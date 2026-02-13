#!/bin/bash
# Setup script for Raspberry Pi 5 Assistive Device

echo "=========================================="
echo "Setup - Sistema de Asistencia a Invidentes"
echo "=========================================="

# Check Python version
if ! command -v python3.11 &> /dev/null; then
    echo "❌ Python 3.11 no encontrado. Por favor instalar:"
    echo "   sudo apt install python3.11 python3.11-venv"
    exit 1
fi

echo "✅ Python 3.11 encontrado"

# Create virtual environment
echo "📦 Creando entorno virtual..."
python3.11 -m venv venv

# Activate venv
source venv/bin/activate

# Upgrade pip
echo "⬆️  Actualizando pip..."
pip install --upgrade pip

# Install dependencies
echo "📥 Instalando dependencias..."
pip install -r requirements.txt

# Create directories
echo "📁 Creando directorios..."
mkdir -p logs
mkdir -p assets

echo ""
echo "=========================================="
echo "✅ Setup completado"
echo "=========================================="
echo ""
echo "Próximos pasos:"
echo "1. Instalar Hailo SDK y hailo-apps desde:"
echo "   https://github.com/hailo-ai/hailo-rpi5-examples"
echo "2. Activar entorno virtual: source venv/bin/activate"
echo "3. Ejecutar: sudo python3 main.py"
echo ""
echo "📥 El modelo YOLOv8s se descargará automáticamente en el primer uso"
echo ""
