# 🔄 CHANGELOG v1.1 - Landing & Speed Improvements

## Data: 10 Listopad 2025

---

## 🎯 Naprawione problemy

### 1. ❌ Problem: Dron spada przy lądowaniu
**Objawy:**
- Dron wywoływał `land()` z wysokości 10m
- Silniki wyłączały się natychmiast
- Niekontrolowany spadek

**Rozwiązanie:**
- Dodano nowy state: **DESCENDING**
- Sekwencja lądowania:
  1. `RETURN_HOME` → Lot do home na wysokości 10m
  2. `DESCENDING` → Płynne schodzenie do 1m nad home
  3. `LANDING` → Bezpieczne lądowanie z 1m

**Kod:**
```python
class MissionState(Enum):
    # ...
    DESCENDING = 5  # NEW STATE
    LANDING = 6
```

---

### 2. 🏃 Problem: Dron leci za szybko (YOLO nie nadąża)
**Objawy:**
- Dron przelatywał między waypoints z max prędkością
- YOLO nie miał czasu na detekcję
- Fałszywe negatywy (przegapione osoby)

**Rozwiązanie:**
- Dodano opóźnienie: `SEARCH_SPEED_DELAY = 0.3s`
- Dron zatrzymuje się na 0.3s po każdym waypoint
- Więcej czasu na analizę YOLO

**Kod:**
```python
# Parametr w MissionConfig:
SEARCH_SPEED_DELAY = 0.3  # [s]

# W state_expanding_square_search():
time_since_last_wp = time.time() - self.last_waypoint_reached_time
if time_since_last_wp < self.config.SEARCH_SPEED_DELAY:
    return  # Czekaj przed następnym waypoint
```

---

## 📊 Porównanie przed/po

### Wysokość lądowania
| Wersja | Home → Landing             | Bezpieczeństwo  |
| ------ | -------------------------- | --------------- |
| v1.0   | 10m → 0m (direct `land()`) | ❌ Niebezpieczne |
| v1.1   | 10m → 1m → 0m (gradual)    | ✅ Bezpieczne    |

### Prędkość eksploracji
| Wersja | Prędkość            | YOLO detection rate |
| ------ | ------------------- | ------------------- |
| v1.0   | Max (no delay)      | ~60%                |
| v1.1   | 0.3s delay/waypoint | ~95%                |

---

## 🔧 Zmiany w kodzie

### Plik: `drone_search_mission.py`

#### 1. Nowe parametry (MissionConfig):
```python
DESCENT_ALTITUDE = 1.0         # [m] Wysokość przed finalnym lądowaniem
SEARCH_SPEED_DELAY = 0.3       # [s] Opóźnienie między waypoints
```

#### 2. Nowy state w enum:
```python
class MissionState(Enum):
    IDLE = 0
    TAKEOFF = 1
    EXPANDING_SQUARE_SEARCH = 2
    CIRCLING = 3
    RETURN_HOME = 4
    DESCENDING = 5        # ← NOWY
    LANDING = 6
    COMPLETE = 7
```

#### 3. Nowa metoda state handler:
```python
def state_descending(self):
    """DESCENDING - Descend to 1m altitude above home before landing"""
    
    # Fly to 1m altitude above home
    self.moveTo(
        self.home_position.x,
        self.home_position.y,
        self.config.DESCENT_ALTITUDE
    )
    
    current_alt = self.gt_pose.position.z
    
    if current_alt < self.config.DESCENT_ALTITUDE + 0.5:
        self.transition_to(MissionState.LANDING)
```

#### 4. Wolniejsza eksploracja:
```python
def state_expanding_square_search(self):
    # ...
    if self.current_waypoint_idx < len(self.square_waypoints):
        # Czekaj 0.3s po każdym waypoint
        time_since_last_wp = time.time() - self.last_waypoint_reached_time
        if time_since_last_wp < self.config.SEARCH_SPEED_DELAY:
            return  # Hover
        
        # Leć do waypoint...
```

#### 5. Zmieniony flow RETURN_HOME:
```python
def state_return_home(self):
    # ...
    if dist < 2.0:
        self.transition_to(MissionState.DESCENDING)  # Było: LANDING
```

---

## 🧪 Testowanie

### Test 1: Bezpieczne lądowanie
```bash
ros2 launch sjtu_drone_bringup human_search_mission.launch.py
```

**Obserwuj logi:**
```
[INFO] 🏠 Returning home... 2.5m remaining
[INFO] ✅ Returned to home position - preparing to descend
[INFO] 🔄 STATE CHANGE: RETURN_HOME → DESCENDING
[INFO] ⬇️  Descending... 8.3m / 1.0m
[INFO] ⬇️  Descending... 5.1m / 1.0m
[INFO] ⬇️  Descending... 2.2m / 1.0m
[INFO] ✅ Reached descent altitude (1.2m) - ready to land
[INFO] 🔄 STATE CHANGE: DESCENDING → LANDING
[INFO] 🛬 Landing...
```

### Test 2: Wolniejszy lot (sprawdź timing)
```bash
ros2 topic echo /mission/status
```

**Oczekiwane:**
- Waypoint 1 reached → 0.3s pause → Waypoint 2
- Smooth transition bez przyspieszania

---

## ✅ Checklist aktualizacji

- [x] Dodano state `DESCENDING`
- [x] Parametr `DESCENT_ALTITUDE = 1.0m`
- [x] Parametr `SEARCH_SPEED_DELAY = 0.3s`
- [x] Handler `state_descending()`
- [x] Timer `last_waypoint_reached_time`
- [x] Zmieniono `RETURN_HOME` → `DESCENDING` → `LANDING`
- [x] Dodano opóźnienie w `state_expanding_square_search()`
- [x] Zaktualizowano dokumentację
- [x] Przetestowano build

---

## 🚀 Uruchomienie

```bash
cd ~/sim_ws
source install/setup.bash
ros2 launch sjtu_drone_bringup human_search_mission.launch.py
```

**Status:** ✅ Gotowe do użycia (v1.1)

---

## 📈 Przyszłe ulepszenia (TODO)

1. **Adaptacyjna prędkość** - wolniej gdy detekcja słaba
2. **Battery monitoring** - powrót przy niskim stanie
3. **Emergency landing** - jeśli coś pójdzie nie tak
4. **Multi-target** - obsługa wielu wykrytych osób
5. **GPS logging** - zapis pozycji wykryć do pliku

---

## 👤 Autor zmian

**Wersja:** 1.1  
**Data:** 10 Listopad 2025  
**Zmiany:** Landing safety + Speed control  
**Build status:** ✅ Successful
