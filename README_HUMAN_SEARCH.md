# 🚁 Autonomous Drone Human Search Mission

**Autonomiczny dron poszukujący ludzi z wykorzystaniem YOLO v11 i maszyny stanów**

---

## 📋 Spis treści
- [Opis projektu](#opis-projektu)
- [Maszyna stanów](#maszyna-stanów)
- [Uruchomienie - JEDNA KOMENDA](#uruchomienie---jedna-komenda)
- [Monitoring misji](#monitoring-misji)
- [Parametry konfiguracyjne](#parametry-konfiguracyjne)
- [Struktura projektu](#struktura-projektu)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Opis projektu

System autonomicznego drona, który:
1. **Startuje** z miejsca na wysokość 10m i czeka 3 sekundy
2. **Przeszukuje** obszar po rozszerzających się kwadratach (2m → 20m, +2m)
3. **Wykrywa** ludzi za pomocą YOLO v11 (weryfikacja 5 kolejnych klatek, confidence > 0.8)
4. **Zawisa** i wraca do punktu detekcji
5. **Centruje się** precyzyjnie nad wykrytą osobą (PID, tolerancja 0.1m)
6. **Krąży** 2x nad wykrytą osobą (promień 2m)
7. **Wraca** do punktu startu, **schodzi** do 1m i ląduje

### Kluczowe cechy:
- ✅ Detekcja w czasie rzeczywistym (YOLO v11)
- ✅ Weryfikacja wielokrotna (5 kolejnych klatek)
- ✅ Rozszerzające się kwadraty poszukiwania
- ✅ Precyzyjne pozycjonowanie PID
- ✅ Obliczanie pozycji wykrytej osoby na podstawie FOV kamery
- ✅ Wszystkie parametry w jednym miejscu
- ✅ Szczegółowe logi w terminalu

---

## 🔄 Maszyna stanów

```
┌──────────┐
│   IDLE   │ (inicjalizacja)
└────┬─────┘
     │
     ▼
┌──────────┐
│ TAKEOFF  │ ◄─── Start + czekanie 3s
└────┬─────┘      Zapisanie home position
     │
     ▼
┌─────────────────────────┐
│ EXPANDING_SQUARE_SEARCH │ ◄─── Kwadraty: 2m → 4m → 6m → ... → 20m
│     🔍 + YOLO           │      Detekcja w tle (10m wysokość)
└──┬────────────┬─────────┘
   │            │
   │ wykryto    │ nie znaleziono
   │            │
   ▼            ▼
┌───────────┐  ┌──────────────┐
│ HOVERING  │  │ RETURN_HOME  │
│ (powrót)  │  │     🏠       │
└─────┬─────┘  └──────┬───────┘
      │                │
      ▼                │
┌────────────┐         │
│ CENTERING  │         │
│ (PID 0.1m) │         │
└─────┬──────┘         │
      │                │
      ▼                │
┌───────────┐          │
│ CIRCLING  │          │
│ (2x okr.) │          │
└─────┬─────┘          │
      │                │
      └────────┬───────┘
               │
               ▼
        ┌──────────────┐
        │ DESCENDING   │
        │ (do 1m)      │
        └──────┬───────┘
               │
               ▼
        ┌──────────┐
        │ LANDING  │
        └────┬─────┘
             │
             ▼
        ┌──────────┐
        │ COMPLETE │
        └──────────┘
```

### Opis stanów:
- **IDLE** - Inicjalizacja systemu
- **TAKEOFF** - Start na wysokość 10m, zapisanie home position, czekanie 3s
- **EXPANDING_SQUARE_SEARCH** - Poszukiwanie po rozszerzających się kwadratach (2m→20m), detekcja YOLO w tle
- **HOVERING** - Po wykryciu: powrót do punktu detekcji i stabilizacja
- **CENTERING** - Precyzyjne centrowanie nad wykrytą osobą (PID, tolerancja 0.1m)
- **CIRCLING** - Krążenie nad osobą (2 okrążenia, promień 2m)
- **RETURN_HOME** - Powrót do punktu startu na wysokości 10m
- **DESCENDING** - Zniżanie do wysokości 1m nad punktem startu
- **LANDING** - Lądowanie
- **COMPLETE** - Misja zakończona

---

## 🚀 Uruchomienie - JEDNA KOMENDA

### Launch całego systemu:
```bash
cd ~/sim_ws
source install/setup.bash
bash src/scripts/launch_human_search.sh
```

**Co się uruchomi:**
1. Gazebo (symulator)
2. Dron SJTU
3. YOLO detector (detekcja ludzi)
4. Mission controller (autonomiczna misja)


## 📊 Monitoring misji

### Logi w terminalu
System wyświetla szczegółowe informacje:

```
╔══════════════════════════════════════════════════════════╗
║   🚁 DRONE HUMAN SEARCH MISSION - STARTED 🚁           ║
╚══════════════════════════════════════════════════════════╝
📐 Search pattern: 2.0m → 20.0m (increment: 2.0m)
🎯 Detection threshold: 0.8 (5 consecutive frames)
✈️  Flight altitude: 10.0m
──────────────────────────────────────────────────────────
🏠 Home position saved: x=0.0, y=0.0, z=0.0
⬆️  Climbing... 4.3m / 10.0m
✅ Takeoff complete - waiting 3.0s
🔍 Starting search mission...
📍 Waypoint 1/4 reached (square: 2m)
📍 Waypoint 2/4 reached (square: 2m)
🔍 Expanding search - new square size: 4m
🎯 HUMAN CONFIRMED! (avg confidence: 0.85, 5 detections)
╔══════════════════════════════════════════════╗
║  🎯 HUMAN DETECTED! Switching to HOVERING   ║
╚══════════════════════════════════════════════╝
🔄 Returning to detection point... 3.2m
✅ Hovering stabilized! Reading camera...
📐 Calculated human position: x=4.2, y=3.1 (offset from drone)
🎯 Centering over human... 2.1m remaining
✅ Centered above human! (offset: 0.08m)
⭕ Circling... rotation 0.5/2.0
⭕ Circling... rotation 1.0/2.0
⭕ Circling... rotation 1.5/2.0
✅ Circling complete (2.0 rotations)
🏠 Returning home... 8.3m remaining
✅ Returned to home position - preparing to descend
⬇️  Descending... 8.2m / 1.0m
✅ Reached descent altitude (1.1m) - ready to land
🛬 Landing...
╔══════════════════════════════════════════════════════════╗
║        ✅ MISSION COMPLETE - DRONE LANDED ✅            ║
╚══════════════════════════════════════════════════════════╝
```

### ROS2 Topics

**Status misji:**
```bash
ros2 topic echo /mission/status
```

**Detekcje YOLO:**
```bash
ros2 topic echo /detection/human_detected
```

**Pozycja drona:**
```bash
ros2 topic echo /simple_drone/gt_pose
```

**Wizualizacja detekcji (RViz2):**
```bash
# Obraz z bounding boxes
ros2 topic echo /simple_drone/bottom/image_object_detection
```

### Wizualizacja w RViz2

W RViz2 dodaj:
- **Image** display → Topic: `/simple_drone/bottom/image_object_detection`
- **TF** → Zobacz pozycję drona w czasie rzeczywistym
- **Map** → Trajektoria lotu

---

## ⚙️ Parametry konfiguracyjne

**WSZYSTKIE parametry w jednym miejscu:**

Edytuj plik: `sjtu_drone_control/sjtu_drone_control/drone_search_mission.py`

```python
class MissionConfig:
    """Centralized configuration - MODIFY HERE"""
    
    # Search pattern (expanding squares)
    SQUARE_START_SIZE = 2.0      # [m] Początkowy rozmiar kwadratu
    SQUARE_INCREMENT = 2.0        # [m] Przyrost przy każdej iteracji
    SQUARE_MAX_SIZE = 20.0        # [m] Maksymalny rozmiar
    
    # Flight parameters
    SEARCH_ALTITUDE = 10.0        # [m] Wysokość lotu poszukiwawczego
    DESCENT_ALTITUDE = 1.0        # [m] Zniżanie przed lądowaniem
    CIRCLE_RADIUS = 2.0           # [m] Promień krążenia
    CIRCLE_ROTATIONS = 2.0        # Liczba okrążeń
    SEARCH_SPEED_DELAY = 0.5      # [s] Opóźnienie między punktami trasy
    
    # PID Controllers
    PID_KP = 0.8                  # Współczynnik proporcjonalny
    PID_KI = 0.10                 # Współczynnik całkujący
    PID_KD = 0.3                  # Współczynnik różniczkujący
    PID_MAX_VEL = 1.0             # [m/s] Maksymalna prędkość
    
    # Centering
    CENTERING_TOLERANCE = 0.1     # [m] Tolerancja centrowania nad osobą
    
    # Camera parameters
    CAMERA_FOV_HORIZONTAL = 60.0  # [deg] Kąt widzenia poziomy
    CAMERA_FOV_VERTICAL = 33.75   # [deg] Kąt widzenia pionowy
    
    # Detection parameters
    DETECTION_CONFIDENCE_THRESHOLD = 0.8   # Min confidence YOLO
    DETECTION_CONSECUTIVE_FRAMES = 5       # Weryfikacja N klatek
    
    # Timing
    TAKEOFF_WAIT_TIME = 3.0       # [s] Czas oczekiwania po starcie
    WAYPOINT_TOLERANCE = 0.3      # [m] Tolerancja dotarcia do punktu
    
    # Control loop
    CONTROL_LOOP_RATE = 5.0       # [Hz] Częstotliwość pętli
```

**Po zmianie - PAMIETAJ PRZEBUDOWAĆ!:**
```bash
cd ~/sim_ws
colcon build --packages-select sjtu_drone_control
source install/setup.bash
```

---

## 📁 Struktura projektu

```
sjtu_drone_control/
├── drone_search_mission.py       # ← GŁÓWNY kontroler misji
│   ├── MissionConfig              #   Parametry (TUTAJ edytuj)
│   ├── MissionState               #   Stany maszyny
│   └── DroneSearchMission         #   Logika misji
│
├── drone_utils/
│   └── drone_object.py            # Bazowa klasa sterowania dronem
│
└── ...

sjtu_drone_camera/
├── detect_object_by_yolo.py       # ← YOLO detector
│   └── /detection/human_detected  #   Publikuje: {detected, confidence, count}
│
└── models/current_used_model/     # Model YOLO v11
    └── current_used_model.pt

sjtu_drone_bringup/
└── launch/
    └── human_search_mission.launch.py  # ← Launch file (JEDNA KOMENDA)
```

---


## 📝 Changelog

- **v1.2** - Dodano HOVERING, CENTERING, DESCENDING; precyzyjne pozycjonowanie PID; obliczanie pozycji na podstawie FOV
- **v1.1** - Rozszerzono parametry konfiguracyjne (PID, FOV kamery, centering)
- **v1.0** - Autonomiczna misja z YOLO v11, expanding squares, weryfikacja 5 klatek
- **v0.9** - Integracja YOLO z mission controller
- **v0.8** - Podstawowa maszyna stanów

---

**Gotowe do lotu! 🚁**

```bash
ros2 launch sjtu_drone_bringup human_search_mission.launch.py
```
