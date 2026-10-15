# gcheck CLI

[English](README.md) | [中文](README.zh.md) | **Español** | [日本語](README.ja.md)

gcheck es una herramienta ligera de diagnóstico por línea de comandos (CLI) diseñada específicamente para desarrolladores con el fin de simplificar la integración de Google AI. Ya no necesitas escribir scripts improvisados para probar las API: escanea tu configuración automáticamente en segundos, ayudándote a detectar problemas de configuración a tiempo y a ejecutar tu primer "Hello Gemini" sin contratiempos.

---

## ✨ Características principales

- 🚀 **Diagnóstico automatizado de la API de Gemini**: Soluciona al instante los problemas en tus llamadas a la API de Google Gemini. Verifica automáticamente la conectividad de red, los permisos del proyecto en Google Cloud Platform (GCP), las claves de API y la configuración de parámetros del modelo para que te conectes a Gemini más rápido que nunca.
- 📁 **Escaneo inteligente del directorio del proyecto**: Detecta de forma fluida las configuraciones del proyecto directamente en tu espacio de trabajo. Analiza tus archivos de entorno local, dependencias y configuraciones para identificar cuellos de botella ocultos en la integración.
- 🛠️ **Soluciones claras para errores confusos**: No te limites a encontrar el error: corrígelo. Reemplaza los mensajes de error confusos por explicaciones claras y fáciles de entender, y ofrece guías prácticas paso a paso para eliminar el método de prueba y error.

---

## 📋 Requisitos previos

- Python 3.10+
- [pipx](https://pipx.pypa.io/stable/installation/) (recomendado para la instalación; no es necesario si usas `pip` directamente)
- Una clave `GEMINI_API_KEY` (opcional — solo se necesita si quieres verificar la conectividad con la API de Gemini)

---

## 🚀 Instalación

### Instalación rápida (recomendada)

Clona el repositorio y luego ejecuta el script de instalación para tu sistema operativo. El script verifica que tengas Python 3.10+ y `pipx` (instalando cualquiera de los dos si falta) e instala `gcheck` como un comando global y editable — los cambios en el código se aplican de inmediato sin necesidad de reinstalar:

```sh
# macOS / Linux
./install.sh
```

```powershell
# Windows (PowerShell)
.\install.ps1
```

Si macOS/Linux bloquea el script con un error de `permission denied` (permiso denegado), primero dale permisos de ejecución y vuelve a ejecutarlo:

```sh
chmod +x install.sh
./install.sh
```

Si Windows bloquea el script con un error de política de ejecución (execution policy), ejecuta:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

Si no se encuentra el comando `gcheck` justo después de instalarlo, abre una nueva ventana de la terminal — es posible que los scripts acaben de actualizar tu variable `PATH`.

### Instalación manual

| Comando | Entorno virtual aislado | Comando global `gcheck` | Modo editable (los cambios en el código se aplican de inmediato) |
|---|---|---|---|
| `pipx install --editable .` (recomendado) | Sí | Sí | Sí |
| `pipx install .` | Sí | Sí | No — vuelve a ejecutarlo con `--force` después de hacer cambios |
| `pip install -e .` | No, se instala en el entorno activo | Sí, dentro de ese entorno | Sí |
| `pip install --require-hashes -r requirements.txt` | No, se instala en el entorno activo | No — sin punto de entrada; ejecútalo mediante `python -m gcheck` | No aplica |

```sh
# recomendado para desarrollo activo
pipx install --editable .
```

`pip install --require-hashes -r requirements.txt` instala las versiones exactas, fijadas y verificadas por hash desde el archivo de bloqueo (lock file), pero no instala `gcheck` en sí — úsalo para reproducir un conjunto de dependencias probado y luego ejecuta `pip install -e . --no-deps` para obtener el comando `gcheck`.

---

## ⚙️ Configuración

Opcional — solo se necesita para verificar la conectividad de la clave de API. Copia `.env.example` a `.env` en tu directorio de trabajo y agrega tu clave:

```
GEMINI_API_KEY=your_api_key_here
```

---

## 💻 Uso

```sh
gcheck              # Seleccionar idioma en la interfaz de la terminal (TUI)
gcheck --lang en    # Inglés (English)
gcheck --lang zh    # Chino (中文)
gcheck --lang es    # Español
gcheck --lang ja    # Japonés (日本語)
```

---

## 🗑️ Desinstalación

```sh
pipx uninstall gcheck
```

Si aparece `pipx: command not found` — es posible que `install.sh` haya instalado `pipx` mediante `pip install --user` (sin Homebrew), lo cual solo lo agrega a tu `PATH` en ventanas de terminal *nuevas*. Abre una nueva terminal y vuelve a intentarlo, o ejecútalo directamente a través de Python:

```sh
python3 -m pipx uninstall gcheck
```

Si realizaste la instalación con `pip install -e .` en lugar de `pipx`, usa `pip uninstall gcheck` en el mismo entorno donde lo instalaste.

Para eliminar también `pipx`: ejecuta primero `pipx uninstall-all` (elimina todas las aplicaciones administradas por pipx) y luego `pip uninstall pipx` o `brew uninstall pipx`, según cómo hayas instalado `pipx`.

---

## 🧪 Pruebas

La suite de pruebas se ejecuta sobre una copia local del repositorio:

```sh
pip install -e ".[test]"
pytest unit_test
```

El sistema de CI ejecuta la misma suite en cada push y pull request en Ubuntu, macOS y Windows con Python 3.10 y 3.13 — consulta [.github/workflows/unit-tests.yml](.github/workflows/unit-tests.yml). Para ver qué está cubierto y qué se omitió deliberadamente, consulta [unit_test/README.md](unit_test/README.md).

---

## 📄 Licencia

Publicado bajo la Licencia Apache, versión 2.0. Consulta el archivo [LICENSE](LICENSE) para ver el texto completo.
