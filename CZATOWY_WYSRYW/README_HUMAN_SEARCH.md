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
1. **Startuje** z miejsca i czeka 3 sekundy
2. **Przeszukuje** obszar po rozszerzających się kwadratach (2m → 20m, +2m)
3. **Wykrywa** ludzi za pomocą YOLO v11 (weryfikacja 5 kolejnych klatek, confidence > 0.8)
4. **Krąży** 2x nad wykrytą osobą
5. **Wraca** do punktu startu i ląduje

### Kluczowe cechy:
- ✅ Detekcja w czasie rzeczywistym (YOLO v11)
- ✅ Weryfikacja wielokrotna (5 kolejnych klatek)
- ✅ Rozszerzające się kwadraty poszukiwania
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
│     🔍 + YOLO           │      Detekcja w tle
└──┬────────────┬─────────┘
   │            │
   │ wykryto    │ nie znaleziono
   │            │
   ▼            ▼
┌───────────┐  ┌──────────────┐
│ CIRCLING  │  │ RETURN_HOME  │
│ (2x okr.) │  │     🏠       │
└─────┬─────┘  └──────┬───────┘
      │                │
      └────────┬───────┘
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

---

## 🚀 Uruchomienie - JEDNA KOMENDA

### Wymagania:
```bash
# Zainstaluj zależności (raz)
pip install "numpy<2.0" ultralytics opencv-python
```

### Launch całego systemu:
```bash
cd ~/sim_ws
source install/setup.bash

# JEDNA KOMENDA - uruchamia wszystko:
ros2 launch sjtu_drone_bringup human_search_mission.launch.py
```

**Co się uruchomi:**
1. Gazebo (symulator)
2. Dron SJTU
3. YOLO detector (detekcja ludzi)
4. Mission controller (autonomiczna misja)

### Alternatywnie - krok po kroku:

**Terminal 1: Gazebo + Dron**
```bash
ros2 launch sjtu_drone_bringup sjtu_drone_bringup.launch.py
```

**Terminal 2: YOLO Detector (czekaj 5s po uruchomieniu Gazebo)**
```bash
ros2 run sjtu_drone_camera detect_object_by_yolo
```

**Terminal 3: Mission Controller (czekaj aż YOLO załaduje model)**
```bash
ros2 run sjtu_drone_control drone_search_mission
```

---

## 📊 Monitoring misji

### Logi w terminalu
System wyświetla szczegółowe informacje:

```
╔══════════════════════════════════════════════════════════╗
║   🚁 DRONE HUMAN SEARCH MISSION - STARTED 🚁           ║
╚══════════════════════════════════════════════════════════╝
📐 Search pattern: 2.0m → 20.0m (increment: 2.0m)
🎯 Detection threshold: 0.8 (5 consecutive frames)
✈️  Flight altitude: 5.0m
──────────────────────────────────────────────────────────
🏠 Home position saved: x=0.0, y=0.0, z=0.0
⬆️  Climbing... 2.3m / 5.0m
✅ Takeoff complete - waiting 3.0s
🔍 Starting search mission...
📍 Waypoint 1/4 reached (square: 2m)
📍 Waypoint 2/4 reached (square: 2m)
🔍 Expanding search - new square size: 4m
🎯 HUMAN CONFIRMED! (avg confidence: 0.85, 3 detections)
╔══════════════════════════════════════════════╗
║  🎯 HUMAN DETECTED! Switching to CIRCLING   ║
╚══════════════════════════════════════════════╝
⭕ Circling... rotation 0.5/2.0
✅ Circling complete (2.0 rotations)
🏠 Returning home... 8.3m remaining
✅ Returned to home position
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
    SEARCH_ALTITUDE = 5.0         # [m] Wysokość lotu
    CIRCLE_RADIUS = 3.0           # [m] Promień krążenia
    CIRCLE_ROTATIONS = 2.0        # Liczba okrążeń
    
    # Detection parameters
    DETECTION_CONFIDENCE_THRESHOLD = 0.8   # Min confidence YOLO
    DETECTION_CONSECUTIVE_FRAMES = 5       # Weryfikacja N klatek
    
    # Timing
    TAKEOFF_WAIT_TIME = 3.0       # [s] Czas oczekiwania po starcie
    WAYPOINT_TOLERANCE = 0.8      # [m] Tolerancja dotarcia do punktu
    
    # Control loop
    CONTROL_LOOP_RATE = 5.0       # [Hz] Częstotliwość pętli
```

**Po zmianie:**
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

## 🔧 Troubleshooting

### Dron nie startuje
```bash
# Sprawdź czy Gazebo działa
ros2 node list | grep simple_drone

# Sprawdź topiki
ros2 topic list | grep simple_drone
```

### YOLO nie wykrywa
```bash
# Sprawdź czy YOLO publikuje
ros2 topic hz /detection/human_detected

# Zobacz obraz z kamery
ros2 run rqt_image_view rqt_image_view /simple_drone/bottom/image_raw

# Sprawdź wizualizację detekcji
ros2 run rqt_image_view rqt_image_view /simple_drone/bottom/image_object_detection
```

### Błąd NumPy
```bash
pip uninstall numpy -y
pip install "numpy==1.26.4"
```

### Dron lata w złe miejsce
- Sprawdź czy `DroneObject` używa poprawnych topików (`/simple_drone/*`)
- Zobacz: `ros2 topic info /simple_drone/cmd_vel`

### Gazebo działa wolno (1 FPS)
- Usuń `LIBGL_ALWAYS_SOFTWARE` z `devcontainer.json`
- Uruchom bez GUI: zmień w launch `gui:=false`

---

## 🎓 Dalsze informacje

**Zobacz szczegółowy tutorial:**
- [`TUTORIAL.md`](TUTORIAL.md) - Architektura systemu, jak działa każdy stan

**Dokumenty pomocnicze:**
- [`przykładowe_komendy_do_sterowania.txt`](przykładowe_komendy_do_sterowania.txt) - Ręczne sterowanie
- [`MISSION_README.md`](sjtu_drone_control/MISSION_README.md) - Opis misji poszukiwania

---

## 📝 Changelog

- **v1.0** - Autonomiczna misja z YOLO v11, expanding squares, weryfikacja 5 klatek
- **v0.9** - Integracja YOLO z mission controller
- **v0.8** - Podstawowa maszyna stanów

---

## 🤝 Contributing

Projekt w ramach zajęć z robotyki mobilnej.

**Autor:** FHTW Student  
**Data:** Listopad 2025  
**Framework:** ROS2 Iron, Gazebo 11, YOLO v11

---

## 📄 License

GNU GPL v3.0 - zgodnie z licencją projektu sjtu_drone_arl

---

**Gotowe do lotu! 🚁**

```bash
ros2 launch sjtu_drone_bringup human_search_mission.launch.py
```
