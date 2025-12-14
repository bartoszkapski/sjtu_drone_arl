# 🚁 Autonomous Drone Human Search Mission

**Autonomiczny dron poszukujący ludzi z wykorzystaniem YOLO v11 light i maszyny stanów**

---

## 📋 Spis treści
- [Opis projektu](#opis-projektu)
- [Uruchomienie programu](#uruchomienie-programu)
- [Parametry konfiguracyjne](#parametry-konfiguracyjne)
- [Wybór obiektu detekji](#Wybór-obiektu-detekcji)

---

## 🎯 Opis projektu

System autonomicznego drona, który:
1. **Startuje**
2. **Przeszukuje** obszar po rozszerzających się kwadratach
3. **Wykrywa** ludzi za pomocą YOLO v11 light
4. **Zawisa** i wraca do punktu detekcji
5. **Centruje się** precyzyjnie nad wykrytą osobą
6. **Krąży** 2x nad wykrytą osobą 
7. **Wraca** do punktu startu, **schodzi** do 1m i ląduje


---


## 🚀 Uruchomienie programu


## Przed pierwszym uruchomieniem konieczna jest aktualizacja bibliotek odpowiedzlnych za przetwarzanie obrazu kamery
```bash
cd ~/sim_ws
source src/setup_env.sh
source install/setup.bash
bash src/scripts/launch_human_search.sh
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
    # param kwadrat
    SQUARE_START_SIZE = 4.0                 # poczatkowy rozmiar kwadratu
    SQUARE_INCREMENT = 2.0                  # o ile zwiększać
    SQUARE_MAX_SIZE = 20.0                  # max rozmiar kwadratru
    
    # param lot
    SEARCH_ALTITUDE = 10.0                  # wysokośc lotu 
    DESCENT_ALTITUDE = 1.0                  # wyokośc przed lądowaniem
    CIRCLE_RADIUS = 2.0                     # promień krążenia nad obiektem
    CIRCLE_ROTATIONS = 2.0                  # liczba pełnych obrotów nad obiektem

    
    # PID 
    PID_KP = 0.5     
    PID_KI = 0.02     
    PID_KD = 0.5     
    PID_MAX_VEL = 1.0 
    
    # centrowanie
    CENTERING_TOLERANCE = 0.5               # tolerancja odległości
    
    # kamera
    CAMERA_HORIZONTAL = 60.0                # poziomy zakres widzenia
    CAMERA_VERTICAL = 33.75                 # pionowy zakres widzenia
    
    # detekcja YOLO
    DETECTION_CONFIDENCE_THRESHOLD = 0.8    # minimalny próg detekcji
    DETECTION_CONSECUTIVE_FRAMES = 7        # liczba kolejnych klatek potrzebnych
    
    # czasówki
    TAKEOFF_WAIT_TIME = 3.0                 # czas oczekiwania po starcie
    WAYPOINT_TOLERANCE = 1.5                # tolerancja odległości do uznania punktu za osiągnięty
    
    # częstotliwość sterowań
    CONTROL_LOOP_RATE = 5.0      
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
├── drone_search_mission.py       #  GŁÓWNY kontroler misji
│   ├── MissionConfig              #   Parametry (TUTAJ edytuj)
│   ├── MissionState               #   Stany maszyny
│   └── DroneSearchMission         #   Logika misji
│
├── drone_utils/
│   └── drone_object.py            # Bazowa klasa sterowania dronem
│
└── ...

sjtu_drone_camera/
├── detect_object_by_yolo.py       #  YOLO detector
│   └── /detection/human_detected  #  publikuje: {detected, confidence, count}
│
└── models/current_used_model/     # model yolov11
    └── current_used_model.pt

sjtu_drone_bringup/
└── launch/
    └── human_search_mission.launch.py  # Launch file (JEDNA KOMENDA)
```

---


**Wybór obiektu detekji**
Detekcja obiektu jest uzależniona od obecnego modelu current_used_model.pt znajdującego się w folderze:
```bash
/home/fhtw_user/sim_ws/src/sjtu_drone_camera/models/current_used_model
```

Można załadować istniejący model, lub przeprowadzić krótki proces uczenia nowego modelu detekcji na wybranym obiekcie.

Podczas uruchomionego środowiska można zapisać obecną klatkę obrazu dolnej kamery drona do pliku w celu wyuczenia na nim modelu detekcji.
```bash
ros2 run sjtu_drone_camera image_saver
```

W celu wyuczenia nowego modelu detekcji trzeba skorzystać z poniższych skryptów:
- Wyznaczenie obiektu + albumentacja
```bash
cd /home/fhtw_user/sim_ws/src/sjtu_drone_camera/scripts/
python3 load_image.py --image ../target_images/human.jpg --bbox false
```
- traning modelu
```bash
python3 train_model.py --album ../albums/album_human --class-name human --epochs 20 --batch 4
```

- ewentualna walidacja wyuczonego modelu
```bash
python3 test_model.py --weights ../models/album_human_human_finetune/weights/best.pt --source ../albums/album_human/val/images
```

- wybór aktualnie używanego modelu detekcji przez drona
```bash
python3 load_model.py ../models/album_human_human_finetune/weights/best.pt
```




---

**Gotowe do lotu! 🚁**

```bash
ros2 launch sjtu_drone_bringup human_search_mission.launch.py
```
