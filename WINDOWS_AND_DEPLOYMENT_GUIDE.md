# Guía de Compilación, Ejecución en Windows y Despliegue Online de Gymsis

Esta guía detalla las tres maneras de utilizar Gymsis en producción o en recepción:

---

## Opción 1: Ejecución Inmediata en Windows (Recomendada - 1 Clic)

No requiere compilación previa y abre Gymsis directamente como **App de Escritorio Nativa** (sin necesidad de navegador):

1. Abre la carpeta del proyecto en Windows.
2. Haz doble clic en el archivo:
   ```cmd
   Gymsis_Windows_Launcher.bat
   ```
3. El lanzador:
   - Cierra automáticamente cualquier proceso viejo o instancia zombi de Python que tenga ocupado el puerto `8550`.
   - Verifica tu entorno virtual `.venv` e instala las dependencias necesarias.
   - Te permite elegir entre:
     - **Opción 1 (Predeterminada):** Ventana de Escritorio Nativa (App de escritorio tradicional, rápida, sin navegador).
     - **Opción 2:** Servidor Web local en `http://localhost:8550/` (ideal si deseas conectar tablets o el Kiosco remoto).
4. Al cerrar la ventana, el sistema cierra ordenadamente y sincroniza la base de datos `data/gymsis.db` en modo WAL sin pérdida de información.

---

## Opción 2: Compilar a Ejecutable Nativo `.exe` para Windows

Si deseas distribuir un archivo ejecutable único:

1. Ejecuta el script de compilación automática:
   ```cmd
   build_windows_exe.bat
   ```
2. El script instalará `pyinstaller` (si no lo tienes) y compilará el proyecto usando la receta [packaging/gymsis.spec](file:///home/dixon/Desktop/GymSystem/packaging/gymsis.spec).
3. Al finalizar, tu ejecutable estará listo en:
   ```text
   dist\Gymsis.exe
   ```
4. Puedes mover la carpeta `dist\` a cualquier computadora con Windows o poner un acceso directo en el escritorio.

---

## Opción 3: Despliegue Online en la Nube (Acceso Remoto / Multi-Sucursal)

Si deseas tener Gymsis accesible por internet desde cualquier teléfono, tablet o computadora sin depender de una PC fija:

### A. Con Docker y PostgreSQL (Incluido en el proyecto)
El proyecto incluye [docker-compose.yml](file:///home/dixon/Desktop/GymSystem/docker-compose.yml) configurado:
```bash
docker compose up -d --build
```
Esto levantará:
- **gymsis-postgres:** Base de datos relacional PostgreSQL con persistencia en volumen `postgres_data`.
- **gymsis:** Servidor web optimizado con renderizado CanvasKit en el puerto `8550`.

### B. En Plataformas Cloud (Railway, Render, DigitalOcean o VPS)
1. **Variables de entorno a configurar:**
   ```env
   GYMSIS_RUN_MODE=web
   GYMSIS_HOST=0.0.0.0
   GYMSIS_PORT=8550
   GYMSIS_WEB_RENDERER=canvaskit
   GYMSIS_USE_DB=true
   DATABASE_URL=postgresql://usuario:password@host:5432/gymsis
   ```
2. Al conectar la variable `DATABASE_URL` con tu base de datos PostgreSQL en la nube, todos los cajeros, administradores y la pantalla de entrada del kiosco compartirán la misma información en tiempo real sin desfases.

---

## Persistencia y Seguridad de Turnos y Caja

- Si el software o la PC se apagan de improvisto:
  - Todas las ventas, membresías y registros de acceso quedan guardados en el disco inmediatamente (commit sincrónico).
  - Al volver a abrir Gymsis, la función de corte pendiente detectará si el día anterior quedó sin cerrar y generará automáticamente los reportes consolidados en formato **Excel (.xlsx)** y **Texto (.txt)** en la carpeta `reports/`.
  - También puedes hacer un **cierre manual anticipado** en cualquier momento desde la pestaña **Reportes del Turno** con el botón **"Cerrar Turno Ahora (Arqueo)"**.
