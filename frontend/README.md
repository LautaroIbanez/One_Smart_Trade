# One Smart Trade - Frontend

Frontend React/Vite para el dashboard de One Smart Trade.

## Setup

```bash
# Instalar dependencias
pnpm install
```

## Desarrollo

### Inicio Local (Backend en localhost:8000)

```bash
# Asegúrate de que el backend esté corriendo en http://localhost:8000
# Luego inicia el frontend:
pnpm run dev
```

El frontend estará disponible en `http://localhost:5173`. Las peticiones a `/api/*` se proxifican automáticamente a `http://localhost:8000` mediante la configuración de Vite.

### Desarrollo con Backend Remoto

Si el backend corre en otro host/puerto, configura `VITE_API_BASE_URL`:

1. **Crea un archivo `.env` en el directorio `frontend/`:**

```bash
# Copia el ejemplo
cp .env.example .env
```

2. **Edita `.env` y define la URL del backend:**

```env
# Ejemplo: Backend en otro puerto local
VITE_API_BASE_URL=http://localhost:8000

# Ejemplo: Backend remoto
VITE_API_BASE_URL=https://api.example.com

# Ejemplo: Backend en otra máquina de la red local
VITE_API_BASE_URL=http://192.168.1.100:8000
```

3. **Reinicia el servidor de desarrollo:**

```bash
# Detén el servidor (Ctrl+C) y reinicia
pnpm run dev
```

**Importante:** Vite solo inyecta variables de entorno que empiezan con `VITE_` y solo las carga al iniciar el servidor. Debes reiniciar el servidor después de cambiar `.env`.

### Verificar la Configuración

Para verificar que las peticiones van al backend correcto:

1. Abre las DevTools del navegador (F12)
2. Ve a la pestaña "Network"
3. Busca peticiones que empiecen con `/api/v1/`
4. Verifica que la URL completa apunte al backend correcto

## Configuración de Entornos

### Desarrollo Local (Default)

**No requiere configuración adicional.** El proxy de Vite maneja las peticiones automáticamente.

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000` (proxificado automáticamente)
- `VITE_API_BASE_URL`: No definida (usa proxy de Vite)

### Desarrollo con Backend Remoto

**Requiere `VITE_API_BASE_URL` en `.env`**

- Frontend: `http://localhost:5173`
- Backend: URL remota (definida en `VITE_API_BASE_URL`)
- `VITE_API_BASE_URL`: `https://api.staging.example.com` (ejemplo)

### Producción (Same Origin)

**No requiere configuración si frontend y backend están en el mismo dominio.**

- Frontend: `https://app.example.com`
- Backend: `https://app.example.com/api` (mismo dominio)
- `VITE_API_BASE_URL`: No definida (usa `window.location.origin`)

### Producción (Cross-Origin)

**Requiere `VITE_API_BASE_URL` en el build.**

- Frontend: `https://app.example.com`
- Backend: `https://api.example.com` (diferente dominio)
- `VITE_API_BASE_URL`: `https://api.example.com` (definida en `.env.production` o variables de entorno del servidor)

## Variables de Entorno

### VITE_API_BASE_URL

**Descripción:** URL base del backend API.

**Valores por entorno:**

| Entorno | Valor Recomendado | Notas |
|---------|-------------------|-------|
| Desarrollo local | No definida | Usa proxy de Vite |
| Desarrollo remoto | `http://localhost:PORT` o `https://api.staging.com` | URL completa del backend |
| Producción (same origin) | No definida | Usa `window.location.origin` |
| Producción (cross-origin) | `https://api.production.com` | URL completa del backend |

**Ejemplos:**

```env
# Desarrollo local (no necesario, pero puedes especificarlo)
VITE_API_BASE_URL=http://localhost:8000

# Desarrollo con backend remoto
VITE_API_BASE_URL=https://api.staging.example.com

# Producción cross-origin
VITE_API_BASE_URL=https://api.production.example.com
```

## Build

```bash
# Build para producción
pnpm run build

# Preview del build
pnpm run preview
```

**Nota:** Para producción, asegúrate de definir `VITE_API_BASE_URL` antes del build o configurarla en las variables de entorno del servidor donde se despliega el frontend.

## Testing

```bash
# Ejecutar tests
pnpm run test

# Tests con coverage
pnpm run test:coverage
```

## Estructura del Proyecto

```
frontend/
├── src/
│   ├── api/           # Cliente API y hooks de React Query
│   ├── components/    # Componentes React
│   ├── features/      # Features organizados por dominio
│   ├── pages/         # Páginas/rutas
│   ├── services/      # Servicios y utilidades
│   └── utils/         # Utilidades generales
├── .env.example       # Ejemplo de variables de entorno
├── vite.config.ts     # Configuración de Vite
└── package.json       # Dependencias y scripts
```

## Solución de Problemas

### Error: "ECONNREFUSED" o "Network Error"

**Causa:** El backend no está accesible en la URL configurada.

**Solución:**
1. Verifica que el backend esté corriendo
2. Verifica que `VITE_API_BASE_URL` (si está definida) apunte a la URL correcta
3. Verifica que no haya problemas de CORS si el backend está en otro dominio
4. Revisa la consola del navegador para ver la URL exacta que se está usando

### Las peticiones van a localhost:8000 aunque configuré VITE_API_BASE_URL

**Causa:** No reiniciaste el servidor de desarrollo después de cambiar `.env`.

**Solución:**
1. Detén el servidor (Ctrl+C)
2. Reinicia con `pnpm run dev`
3. Verifica que las variables se cargaron: `console.log(import.meta.env.VITE_API_BASE_URL)` en el código

### El proxy de Vite no funciona

**Causa:** Si defines `VITE_API_BASE_URL`, el proxy de Vite se ignora (por diseño).

**Solución:**
- Si quieres usar el proxy: No definas `VITE_API_BASE_URL` o déjala vacía
- Si quieres usar un backend remoto: Define `VITE_API_BASE_URL` con la URL completa

## Más Información

- [Documentación de Vite](https://vitejs.dev/)
- [React Query](https://tanstack.com/query/latest)
- [Backend README](../backend/README.md)

