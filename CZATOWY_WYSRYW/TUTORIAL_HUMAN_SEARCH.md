# 🎓 Tutorial: Autonomiczna Misja Poszukiwania Ludzi

**Szczegółowy przewodnik po architekturze i implementacji**

---

## 📚 Spis treści
1. [Architektura systemu](#architektura-systemu)
2. [Przepływ danych](#przepływ-danych)
3. [Szczegóły implementacji stanów](#szczegóły-implementacji-stanów)
4. [Detekcja YOLO](#detekcja-yolo)
5. [Modyfikacja i rozszerzanie](#modyfikacja-i-rozszerzanie)
6. [Debugowanie](#debugowanie)

---

## 🏗️ Architektura systemu

### Komponenty

```
┌─────────────────────────────────────────────────────────────┐
│                    GAZEBO SIMULATOR                         │
│  • Fizyka drona                                             │
│  • Środowisko 3D                                            │
│  • Sensory (kamera, IMU, GPS, sonar)                        │
└────────────────┬───────────────────────────┬────────────────┘
                 │                           │
                 ▼                           ▼
    ┌────────────────────┐      ┌───────────────────────┐
    │  YOLO DETECTOR     │      │  DRONE OBJECT         │
    │  detect_object.py  │      │  drone_object.py      │
    │                    │      │  • takeOff/land       │
    │  • Subscribe:      │      │  • moveTo(x,y,z)      │
    │    /bottom/image   │      │  • posCtrl            │
    │  • Publish:        │      │  • Publishers/Subs    │
    │    /detection/...  │      └───────────┬───────────┘
    │    /image_detect   │                  │
    └────────┬───────────┘                  │
             │                              │
             └──────────────┬───────────────┘
                            │
                            ▼
              ┌─────────────────────────────┐
              │  MISSION CONTROLLER         │
              │  drone_search_mission.py    │
              │                             │
              │  • State Machine (6 states)│
              │  • Detection verification  │
              │  • Waypoint generation     │
              │  • Control loop (5 Hz)     │
              └─────────────────────────────┘
```

### Node'y i topiki

#### 1. **YOLO Detector Node** (`detect_object_by_yolo`)

**Subscribers:**
- `/simple_drone/bottom/image_raw` (Image) - obraz z kamery dolnej

**Publishers:**
- `/simple_drone/bottom/image_object_detection` (Image) - wizualizacja z bbox
- `/detection/human_detected` (String/JSON) - wyniki detekcji

**Funkcja:**
```json
{
  "detected": bool,      // Czy wykryto człowieka
  "confidence": float,   // Max confidence (0.0-1.0)
  "count": int          // Liczba detekcji w klatce
}
```

#### 2. **Mission Controller Node** (`drone_search_mission`)

**Subscribers:**
- `/detection/human_detected` (String) - wyniki YOLO
- `/simple_drone/gt_pose` (Pose) - pozycja drona (z DroneObject)
- `/simple_drone/imu` (Imu) - orientacja (z DroneObject)
- `/simple_drone/state` (Int8) - stan drona (z DroneObject)

**Publishers:**
- `/mission/status` (String/JSON) - status misji
- `/simple_drone/takeoff` (Empty) - komenda start
- `/simple_drone/land` (Empty) - komenda lądowanie
- `/simple_drone/cmd_vel` (Twist) - sterowanie pozycją
- `/simple_drone/posctrl` (Bool) - tryb kontroli pozycji

---

## 🔄 Przepływ danych

### 1. Inicjalizacja

```
START
  ↓
Mission Controller: __init__()
  ├─ Ładowanie konfiguracji (MissionConfig)
  ├─ Subskrypcja /detection/human_detected
  ├─ Uruchomienie control_timer (5 Hz)
  └─ Stan: IDLE
```

### 2. Pętla główna (control_loop)

```python
def control_loop(self):
    """Main loop - 5 Hz"""
    
    # 1. Publikuj status misji
    status = {
        'state': current_state,
        'square_size': ...,
        'detections_buffer': ...,
        ...
    }
    pub_mission_status.publish(status)
    
    # 2. Wykonaj logikę aktualnego stanu
    if current_state == TAKEOFF:
        state_takeoff()
    elif current_state == EXPANDING_SQUARE_SEARCH:
        state_expanding_square_search()
    # ...
```

### 3. Detekcja w tle

```
YOLO: callback_read_image()
  ├─ Odbiór klatki z kamery
  ├─ Inference YOLO (model.predict)
  ├─ Wizualizacja (plot bboxes)
  └─ Publikacja:
      ├─ /image_object_detection (Image)
      └─ /detection/human_detected (JSON)
          ↓
Mission: cb_detection()
  ├─ Parse JSON
  ├─ Sprawdź confidence > threshold
  ├─ Dodaj do bufora
  ├─ Sprawdź ostatnie N klatek
  └─ Jeśli wszystkie OK:
      └─ human_detected_confirmed = True
```

---

## 🎯 Szczegóły implementacji stanów

### STATE 1: TAKEOFF

**Cel:** Wystartować i ustabilizować na wysokości poszukiwania

```python
def state_takeoff(self):
    current_height = self.gt_pose.position.z
    elapsed = time.time() - self.state_start_time
    
    # KROK 1: Zapisz home position (raz, na początku)
    if elapsed < 0.5:
        self.home_position = self.gt_pose.position  # ← DO POWROTU
        self.posCtrl(True)  # Włącz kontrolę pozycji
        if current_height < 0.5:
            self.takeOff()  # Komenda start
    
    # KROK 2: Wspinaczka do docelowej wysokości
    if current_height < SEARCH_ALTITUDE * 0.9:
        self.moveTo(home_x, home_y, SEARCH_ALTITUDE)
        # Logi: "Climbing... X.Xm / 5.0m"
    
    # KROK 3: Czekanie po osiągnięciu wysokości
    else:
        if elapsed >= TAKEOFF_WAIT_TIME + 5.0:  # 3s wait
            self.generate_square_waypoints()  # ← Generuj pierwszy kwadrat
            transition_to(EXPANDING_SQUARE_SEARCH)
```

**Wyjście:** Dron na wysokości 5m, czekał 3s, home_position zapisana

---

### STATE 2: EXPANDING_SQUARE_SEARCH

**Cel:** Latać po kwadratach (2m → 4m → 6m → ... → 20m) i szukać człowieka

```python
def state_expanding_square_search(self):
    
    # PRIORYTET 1: Sprawdź czy wykryto (5 kolejnych klatek)
    if self.human_detected_confirmed:
        self.circle_center = (current_x, current_y)  # ← Gdzie krążyć
        transition_to(CIRCLING)
        return
    
    # KROK 1: Leć do aktualnego waypoint
    if current_waypoint_idx < len(square_waypoints):
        wp = square_waypoints[current_waypoint_idx]
        self.moveTo(wp[0], wp[1], wp[2])
        
        # Sprawdź czy dotarliśmy (distance < 0.8m)
        if distance_to_point(wp) < WAYPOINT_TOLERANCE:
            current_waypoint_idx += 1
            # Log: "Waypoint 1/4 reached (square: 2m)"
    
    # KROK 2: Zakończono aktualny kwadrat - powiększ
    else:
        current_square_size += SQUARE_INCREMENT  # +2m
        
        if current_square_size > SQUARE_MAX_SIZE:  # > 20m
            # Nie znaleziono - wracaj
            transition_to(RETURN_HOME)
            return
        
        # Generuj nowy, większy kwadrat
        self.generate_square_waypoints()
        current_waypoint_idx = 0
        # Log: "Expanding search - new square: 4m"
```

**Generowanie waypoints:**

```python
def generate_square_waypoints(self):
    """Tworzy 4 rogi kwadratu wokół aktualnej pozycji"""
    half = current_square_size / 2
    center_x = gt_pose.position.x
    center_y = gt_pose.position.y
    z = SEARCH_ALTITUDE
    
    # 4 rogi (kwadrat)
    self.square_waypoints = [
        (center_x + half, center_y + half, z),  # NE (północny-wschód)
        (center_x + half, center_y - half, z),  # SE (południowy-wschód)
        (center_x - half, center_y - half, z),  # SW (południowy-zachód)
        (center_x - half, center_y + half, z),  # NW (północny-zachód)
    ]
```

**Przykład trajektorii:**

```
Kwadrat 1 (2m):
    NW ─────── NE
    │           │
    │     ●     │  ← Start (center)
    │           │
    SW ─────── SE

Kwadrat 2 (4m):
    NW ─────────── NE
    │               │
    │               │
    │       ●       │
    │               │
    │               │
    SW ─────────── SE
```

---

### STATE 3: CIRCLING

**Cel:** Krążyć 2x nad wykrytą osobą

```python
def state_circling(self):
    
    # KROK 1: Oblicz kąt (przyrost ~3° przy 5Hz = 6s/obrót)
    self.circle_angle += 0.05  # radians
    total_rotations = circle_angle / (2 * pi)  # Ile pełnych obrotów
    
    # KROK 2: Sprawdź czy ukończono 2 obroty
    if total_rotations >= CIRCLE_ROTATIONS:  # >= 2.0
        transition_to(RETURN_HOME)
        return
    
    # KROK 3: Oblicz pozycję na okręgu
    x = circle_center[0] + CIRCLE_RADIUS * cos(circle_angle)
    y = circle_center[1] + CIRCLE_RADIUS * sin(circle_angle)
    z = SEARCH_ALTITUDE
    
    self.moveTo(x, y, z)
    
    # Log co ~45° (8 razy na obrót)
    if int(circle_angle * 8) % 8 == 0:
        # "Circling... rotation 0.5/2.0"
```

**Trajektoria krążenia:**

```
      N (0°)
       ↑
   ────●────   ← Start krążenia
  /         \
 │           │
W│     ◉     │E  ← Wykryta osoba (circle_center)
 │           │
  \         /
   ─────────
       ↓
      S (180°)

Promień = 3m
2 pełne obroty
```

---

### STATE 4: RETURN_HOME

**Cel:** Wrócić do punktu startu (home_position)

```python
def state_return_home(self):
    
    # KROK 1: Leć do home
    self.moveTo(
        home_position.x,
        home_position.y,
        SEARCH_ALTITUDE  # Tą samą wysokością
    )
    
    # KROK 2: Sprawdź odległość
    home_wp = (home_position.x, home_position.y, SEARCH_ALTITUDE)
    dist = distance_to_point(home_wp)
    
    # KROK 3: Czy dotarliśmy?
    if dist < 1.0:  # Tolerancja 1m
        transition_to(LANDING)
    else:
        # Log co 2s: "Returning home... 8.3m remaining"
```

---

### STATE 5: LANDING

```python
def state_landing(self):
    self.land()  # Komenda lądowania
    
    if time.time() - state_start_time > 5.0:
        transition_to(COMPLETE)
```

---

### STATE 6: COMPLETE

```python
def state_complete(self):
    # Log: "✅ MISSION COMPLETE"
    self.control_timer.cancel()  # Zatrzymaj pętlę
```

---

## 🔍 Detekcja YOLO

### Callback w YOLO detector

```python
def callback_read_image(self, msg: Image):
    if self._busy:
        return  # Pomiń jeśli poprzedni inference trwa
    
    self._busy = True
    
    # 1. Konwersja ROS Image → OpenCV (BGR numpy)
    cv_bgr = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
    
    # 2. Inference YOLO
    results = self.model.predict(
        source=cv_bgr,
        imgsz=640,
        conf=0.25,  # Próg confidence (wstępny)
        classes=[0],  # Filtr: tylko 'human'
        device="cpu",
        verbose=False
    )
    
    # 3. Wizualizacja (rysuj bounding boxes)
    vis_bgr = results[0].plot()
    self.pub.publish(vis_bgr)  # → /image_object_detection
    
    # 4. Ekstrakcja info o detekcji
    detection_result = {
        "detected": len(boxes) > 0,
        "confidence": max(boxes.conf),  # Najwyższy
        "count": len(boxes)
    }
    self.pub_detection.publish(json.dumps(detection_result))
    
    self._busy = False
```

### Weryfikacja w Mission Controller

```python
def cb_detection(self, msg: String):
    data = json.loads(msg.data)
    detected = data['detected']
    confidence = data['confidence']
    
    # Dodaj do bufora jeśli confidence > threshold
    if detected and confidence >= 0.8:
        self.detection_buffer.append(confidence)
        
        # Ogranicz rozmiar bufora (ostatnie N+5 klatek)
        if len(detection_buffer) > 10:
            detection_buffer = detection_buffer[-10:]
        
        # Sprawdź ostatnie N klatek
        if len(detection_buffer) >= 5:  # DETECTION_CONSECUTIVE_FRAMES
            last_5 = detection_buffer[-5:]
            
            # Czy wszystkie >= 0.8?
            if all(c >= 0.8 for c in last_5):
                avg_conf = sum(last_5) / 5
                # Log: "HUMAN CONFIRMED! (avg: 0.85)"
                self.human_detected_confirmed = True
    else:
        # Brak detekcji - wyczyść bufor (strict)
        detection_buffer.clear()
```

**Dlaczego 5 kolejnych klatek?**
- Eliminuje false positives (pojedyncze błędne detekcje)
- Wymaga stabilnej detekcji przez ~1 sekundę (przy 5 Hz)
- Zwiększa pewność przed krążeniem

---

## 🛠️ Modyfikacja i rozszerzanie

### 1. Zmiana parametrów poszukiwania

**Plik:** `drone_search_mission.py`

```python
class MissionConfig:
    # Zmień kwadraty: 4m → 30m, co 3m
    SQUARE_START_SIZE = 4.0
    SQUARE_INCREMENT = 3.0
    SQUARE_MAX_SIZE = 30.0
    
    # Większy threshold = mniej false positives
    DETECTION_CONFIDENCE_THRESHOLD = 0.9
    
    # Więcej klatek = większa pewność (ale wolniej reaguje)
    DETECTION_CONSECUTIVE_FRAMES = 10
```

### 2. Dodanie nowego stanu (np. PHOTO)

```python
class MissionState(Enum):
    # ...existing...
    PHOTO = 7  # ← Nowy stan: zrób zdjęcie

def state_photo(self):
    """Zrób zdjęcie wykrytej osoby"""
    # Zatrzymaj się nad obiektem
    self.moveTo(
        circle_center[0],
        circle_center[1],
        SEARCH_ALTITUDE - 2.0  # Niżej dla lepszego zdjęcia
    )
    
    # Poczekaj 3s (stabilizacja)
    if time.time() - state_start_time > 3.0:
        # Zapisz obraz
        self.save_current_frame()
        transition_to(RETURN_HOME)
```

Dodaj przejście w `state_circling()`:

```python
def state_circling(self):
    if total_rotations >= CIRCLE_ROTATIONS:
        transition_to(PHOTO)  # ← Zamiast RETURN_HOME
```

### 3. Spirala zamiast kwadratów

Zmień `generate_square_waypoints()`:

```python
def generate_spiral_waypoints(self):
    """Spirala Archimedesa zamiast kwadratów"""
    waypoints = []
    a = 0.5  # Przyrost promienia na obrót
    
    for theta in range(0, 720, 30):  # 2 obroty po 30°
        r = a * math.radians(theta)
        x = center_x + r * cos(math.radians(theta))
        y = center_y + r * sin(math.radians(theta))
        waypoints.append((x, y, SEARCH_ALTITUDE))
    
    self.square_waypoints = waypoints
```

### 4. Dodanie logowania do pliku

```python
import logging

class DroneSearchMission(DroneObject):
    def __init__(self):
        # ...existing...
        
        # Setup file logger
        file_handler = logging.FileHandler('/tmp/mission_log.txt')
        file_handler.setLevel(logging.INFO)
        self.file_logger = logging.getLogger('mission')
        self.file_logger.addHandler(file_handler)
    
    def transition_to(self, new_state):
        # ...existing terminal log...
        
        # Dodatkowo do pliku
        self.file_logger.info(f'{time.time()},{self.current_state.name},{new_state.name}')
```

---

## 🐛 Debugowanie

### Problem: Dron nie wykrywa człowieka

**Kroki:**

1. **Sprawdź czy YOLO działa:**
```bash
ros2 topic hz /detection/human_detected
# Powinno być ~30 Hz (częstotliwość kamery)
```

2. **Zobacz detekcje:**
```bash
ros2 topic echo /detection/human_detected
# Sprawdź "confidence" - czy > 0.8?
```

3. **Wizualizuj w RViz:**
```bash
ros2 run rqt_image_view rqt_image_view /simple_drone/bottom/image_object_detection
# Czy widać bounding boxy?
```

4. **Obniż threshold tymczasowo:**
```python
DETECTION_CONFIDENCE_THRESHOLD = 0.5  # Było 0.8
DETECTION_CONSECUTIVE_FRAMES = 3       # Było 5
```

### Problem: Dron lata w złe miejsce

**Debug waypoints:**

```python
def state_expanding_square_search(self):
    wp = self.square_waypoints[self.current_waypoint_idx]
    
    # DODAJ DEBUG LOG:
    self.logger.info(f'DEBUG: target=({wp[0]:.1f}, {wp[1]:.1f}, {wp[2]:.1f}), '
                     f'current=({pos.x:.1f}, {pos.y:.1f}, {pos.z:.1f}), '
                     f'distance={dist:.2f}m')
```

**Sprawdź moveTo:**

```bash
# Zobacz komendy wysyłane do drona
ros2 topic echo /simple_drone/cmd_vel
```

### Problem: Detection buffer nie działa

**Debug callback:**

```python
def cb_detection(self, msg: String):
    data = json.loads(msg.data)
    
    # DODAJ LOGI:
    self.logger.info(f'DEBUG Detection: detected={data["detected"]}, '
                     f'conf={data["confidence"]:.2f}, '
                     f'buffer_size={len(self.detection_buffer)}')
    
    if len(self.detection_buffer) >= 5:
        last_5 = self.detection_buffer[-5:]
        self.logger.info(f'DEBUG Last 5: {[f"{c:.2f}" for c in last_5]}')
```

### Problem: Kontrola pozycji nie działa

```bash
# Sprawdź czy position control włączona
ros2 topic echo /simple_drone/posctrl

# Sprawdź actual pose
ros2 topic echo /simple_drone/gt_pose

# Sprawdź czy dron odbiera komendy
ros2 topic echo /simple_drone/cmd_mode
```

---

## 📊 Metryki wydajności

### Typowe czasy:

- **Takeoff:** ~8 sekund (5m + 3s wait)
- **Kwadrat 2m:** ~15 sekund
- **Kwadrat 4m:** ~25 sekund
- **Kwadrat 6m:** ~35 sekund
- **Circling (2x):** ~12 sekund
- **Return home:** zależnie od odległości (~20-60s)
- **Landing:** ~5 sekund

**Całkowity czas misji (bez detekcji):**
- Min (znaleziono w pierwszym kwadracie): ~35s
- Max (całe 20m): ~4-5 minut

### Zużycie zasobów:

- **CPU:** ~40% (YOLO na CPU)
- **RAM:** ~1.5 GB
- **GPU (opcjonalnie):** ~20% (YOLO na GPU - 10x szybciej)

---

## 🎯 Best Practices

1. **Zawsze testuj na małych kwadratach:**
   ```python
   SQUARE_START_SIZE = 2.0
   SQUARE_MAX_SIZE = 6.0  # Nie 20.0
   ```

2. **Używaj verbose logów podczas developmentu:**
   ```python
   self.logger.set_level(rclpy.logging.LoggingSeverity.DEBUG)
   ```

3. **Weryfikuj detekcje wizualnie (RViz) przed autonomicznym lotem**

4. **Backup home position:**
   ```python
   if self.home_position is None:
       self.home_position = Pose()  # Fallback (0,0,0)
   ```

5. **Emergency stop:**
   ```bash
   # W razie problemów:
   ros2 topic pub --once /simple_drone/land std_msgs/msg/Empty
   ```

---

## 🚀 Następne kroki

**Możliwe rozszerzenia:**

1. **Multi-target:** Wykrywanie wielu osób, krążenie nad każdą
2. **Adaptacyjna wysokość:** Niżej gdy detection słaba
3. **Frontier exploration:** Zamiast sztywnych kwadratów
4. **GPS waypoints:** Zapisywanie lokalizacji wykrytych osób
5. **Battery monitoring:** Powrót gdy bateria < 20%
6. **Obstacle avoidance:** Unikanie przeszkód z lidara

---

**Powodzenia! 🚁**

Jeśli masz pytania - sprawdź logi, dodaj debug printy, testuj po kolei każdy stan!
