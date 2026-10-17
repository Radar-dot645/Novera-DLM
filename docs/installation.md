# Instalasi

## Termux (utama)

```bash
pkg install python git
termux-setup-storage
cd ~/storage/downloads/Novera-DLM
bash scripts/install-termux.sh
novera
```

Sesuaikan path `cd` dengan lokasi folder hasil ekstrak. `git` opsional kecuali kamu ingin clone repository. Untuk menghindari izin shared storage, instal dari lokasi mana pun yang tersedia lalu atur direktori unduhan ke `~/Novera-Downloads`.

## Linux

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
bash scripts/install-linux.sh
novera
```

## WSL

Jalankan dari shell Ubuntu/WSL. Script WSL memanggil installer Linux.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
bash scripts/install-wsl.sh
novera
```

Installer membuat virtual environment di `~/.local/share/novera/venv` dan launcher `novera`. Ia tidak membutuhkan root selain instalasi paket sistem yang memang dilakukan terpisah.
