#!/usr/bin/env python3
"""
Tworzy puste pliki .txt w folderze labels dla wszystkich obrazów .jpg/.png z folderu images.
Jeśli plik etykiety już istnieje, jest pomijany.
"""

from pathlib import Path


def create_empty_labels():
    """Tworzy puste pliki .txt dla wszystkich obrazów bez etykiet"""
    
    script_dir = Path(__file__).resolve().parent
    images_dir = script_dir / "images"
    labels_dir = script_dir / "labels"
    
    # Upewnij się że foldery istnieją
    if not images_dir.exists():
        print(f"❌ Błąd: Folder images nie istnieje: {images_dir}")
        return
    
    labels_dir.mkdir(exist_ok=True)
    
    # Zbierz wszystkie obrazy
    image_files = []
    image_files.extend(images_dir.glob("*.jpg"))
    image_files.extend(images_dir.glob("*.JPG"))
    image_files.extend(images_dir.glob("*.jpeg"))
    image_files.extend(images_dir.glob("*.JPEG"))
    image_files.extend(images_dir.glob("*.png"))
    image_files.extend(images_dir.glob("*.PNG"))
    
    if not image_files:
        print(f"⚠️  Brak obrazów w folderze: {images_dir}")
        return
    
    created = 0
    skipped = 0
    
    for img_path in sorted(image_files):
        # Nazwa pliku etykiety (ta sama nazwa, rozszerzenie .txt)
        label_name = img_path.stem + ".txt"
        label_path = labels_dir / label_name
        
        if label_path.exists():
            skipped += 1
            print(f"⏭️  Pomijam (już istnieje): {label_name}")
        else:
            # Utwórz pusty plik
            label_path.touch()
            created += 1
            print(f"✅ Utworzono: {label_name}")
    
    print("\n" + "="*60)
    print(f"📊 Podsumowanie:")
    print(f"   Znaleziono obrazów: {len(image_files)}")
    print(f"   Utworzono etykiet:  {created}")
    print(f"   Pominięto:          {skipped}")
    print("="*60)


if __name__ == "__main__":
    create_empty_labels()