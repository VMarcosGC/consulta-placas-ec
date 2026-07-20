# Guión de prueba — versión test del Market (pre-F1)

**Objetivo:** probar el market completo en local, entender su funcionalidad y cerrar la
compuerta M2 con evidencia. Superado esto → checklist de paso a productivo F1 (§4).

---

## 1. Requisitos previos (una sola vez, ~15 min)

| # | Qué | Cómo |
|---|---|---|
| 1 | Cuenta Cloudinary (gratis) | cloudinary.com → registrarse → Dashboard |
| 2 | Credenciales en `.env` local | Copiar del Dashboard: `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` (la sección ya existe en `.env.example`) |
| 3 | Alerta de créditos | Cloudinary → Settings → Usage → notificación al **80 %** (regla del plan de costos §5.1) |
| 4 | Migraciones al día | `alembic current` → debe decir `0018 (head)` ✅ (ya hecho) |
| 5 | 3-6 fotos de un auto real en el celular/PC | Para que la prueba sea realista (motor, carrocería, interior) |

## 2. Levantar la versión test (2 terminales)

```powershell
# Terminal 1 — backend
cd C:\Users\vmarc\OneDrive\Documentos\porpuestas_code\consulta_placas_ec
.\.venv\Scripts\Activate.ps1
python run.py                    # http://localhost:8000

# Terminal 2 — frontend
cd C:\Users\vmarc\OneDrive\Documentos\porpuestas_code\consulta-placas-web
npm run dev                      # http://localhost:3000
```

> Para probar desde el celular (misma red WiFi): abre `http://<IP-de-tu-PC>:3000`.
> El market debe sentirse bien en pantalla chica — ese es tu usuario objetivo.

## 3. Guión de prueba funcional (rol por rol)

Marca cada paso. Cualquier ✗ se anota al pie y se lleva a la sesión de agentes.

### Como VENDEDOR particular (cuenta nueva A)
- [ ] Registro → entra con 5 tokens de cortesía (visible en el badge).
- [ ] Publicar un auto plan **light** (gratis): título, precio, placa válida EC.
- [ ] Llenar la **ficha técnica** por pestañas: solo motor/suspensión primero → guardar →
      verificar que la completitud sube (~17 %) sin exigir el resto.
- [ ] Completar carrocería + interiores + 2 extras ("láminas de seguridad", "llantas nuevas").
- [ ] **Subir fotos**: 3-4 en distintos bloques → aparecen; reordenar; borrar una.
- [ ] Intentar subir 13 fotos → el botón se bloquea al llegar a 12 (y el backend daría 409).
- [ ] Pausar la publicación → editar la ficha estando pausada (deuda M1: ¿funciona ya?).
- [ ] Publicar un segundo auto plan **premium** (cuesta 3 tokens) → saldo baja a 2.
- [ ] Solicitar verificación (100 tokens) → debe dar **402** con copy claro (saldo 2).

### Como COMPRADOR (ventana incógnito, sin cuenta)
- [ ] Feed `/marketplace`: premium arriba con destacado, light abajo; portada = 1ª foto;
      chip "Ficha N % completa".
- [ ] Detalle del anuncio: galería navegable, ficha por bloques legible, extras visibles,
      etiqueta "declarado por el vendedor" en choques/estado motor.
- [ ] La publicación **pausada NO aparece** ni en feed ni por URL directa (404).
- [ ] Consultar la placa del anuncio en la consulta pública (credibilidad cruzada).

### Como ADMIN (tu email en `ADMIN_EMAILS`)
- [ ] Cola de verificaciones vacía funciona sin error; moderación de referencias operativa.

### Técnica (mientras pruebas)
- [ ] En Cloudinary Dashboard: las fotos entraron en la carpeta configurada.
- [ ] Sin errores rojos en la consola del navegador ni en la terminal del backend.
- [ ] Refrescar el feed con datos ya creados: carga < 2 s en local.

**Hallazgos de la prueba:**
- (anotar aquí)

---

## 3-bis. Guión v2 — etapa M2.5 (stand-by de fuentes + wizard + referencias)

Cubre lo entregado en M2.5. **Todo es frontend**: el backend no cambió, así que basta
`npm run dev` con el backend local levantado. Si ya venías del guión §3, no hace falta
recrear las cuentas.

### A. Stand-by de fuentes (SRI y FGE fuera de la UI)

Config: `consulta-placas-web/.env.local` → `NEXT_PUBLIC_FUENTES_INACTIVAS=sri,fge`
(es el default del código; si la variable no existe, el stand-by igual aplica).

- [ ] `/consultar/{placa}` con una placa real → en el **tablero "Fuentes consultadas"** (pie)
      NO aparecen los chips `SRI` ni `FGE`. Sí aparecen `ANT`, `AMT` y `EPMTSD`.
- [ ] En "Consultar en portales oficiales" **NO** está el botón "Valores del SRI".
      Sí sigue "Condición del vehículo" (EPMTSD).
- [ ] **No** se pinta la tarjeta "Valores SRI" en ningún caso.
- [ ] El monto "A pagar" del encabezado **no** incluye valores del SRI.
- [ ] Pie de página: en "Fuentes oficiales" solo se listan **ANT y AMT**.
- [ ] `/precios`: **no** aparecen las filas "Ver valores de matrícula (SRI)" ni
      "Ver alertas legales" (dependen de SRI/FGE).
- [ ] **Prueba de reversibilidad** (la clave de la decisión): poner
      `NEXT_PUBLIC_FUENTES_INACTIVAS=` (vacío) en `.env.local`, reiniciar `npm run dev`
      → SRI y FGE **reaparecen** en todos los puntos anteriores. Dejarlo de nuevo en
      `sri,fge` al terminar.

> Nota: **EPMTSD vuelve a mostrarse** en M2.5 (antes estaba oculto por una lista
> hardcodeada). Es intencional: es una fuente activa vía worker residencial.

### B. Wizard de publicación (3 pasos)

Como **vendedor** con sesión iniciada:

- [ ] `/marketplace/publicar` → se ve la **barra de 3 pasos** (Datos básicos / Ficha técnica /
      Fotos), con el paso 1 resaltado.
- [ ] Llenar datos básicos → el botón dice **"Continuar a la ficha técnica →"**.
- [ ] Al enviar: **NO** te manda al feed; salta **automático al paso 2** con el aviso verde
      "✓ Tu anuncio ya está publicado" y el paso 1 marcado ✓.
- [ ] Paso 2: se ven **las 3 pestañas con TODOS los campos** + extras. Guardar solo
      motor/suspensión → la completitud sube y la **barra inferior** se actualiza en vivo.
- [ ] Botón **"Completar después"** → va a `/marketplace/mis-publicaciones` (no bloquea nada).
- [ ] Volver a entrar, botón **"Continuar a las fotos →"** → paso 3 con el uploader.
- [ ] Paso 3: si la ficha va bajo 100 %, aparece el recuadro ámbar con
      "← Volver a la ficha técnica" y funciona.
- [ ] "Ver mi anuncio publicado" → abre `/marketplace/{id}`.

### C. CTA persistente "Completa tu ficha (N %)"

- [ ] `/marketplace/mis-publicaciones`: toda publicación con ficha < 100 % muestra el botón
      ámbar **"Completa tu ficha (N %)"**.
- [ ] Al hacer clic **abre el editor de ficha** de esa publicación (sin recargar).
- [ ] Guardar un bloque → el **N % del CTA baja/sube en vivo**, sin refrescar la página.
- [ ] Llevar una ficha al **100 %** → el CTA desaparece y queda el chip verde
      **"✓ Ficha completa"**.
- [ ] `/marketplace/{id}` **siendo el dueño y con sesión** → aparece el recuadro ámbar
      "Completa tu ficha (N %)" con el botón "Completar ahora".
- [ ] El mismo `/marketplace/{id}` en **incógnito (sin sesión)** → ese recuadro **NO** aparece.
- [ ] Con la sesión de **otro usuario** → tampoco aparece.

### D. "Ficha incompleta" (< 30 %) — vista del comprador

- [ ] Publicación con ficha bajo 30 % (o sin ficha): en el **feed** la tarjeta muestra
      **"Ficha incompleta"**, NO el chip de porcentaje.
- [ ] En el **detalle público**, junto al título "Ficha técnica", la insignia
      **"Ficha incompleta"** en lugar de la barra de %.
- [ ] Al pasar del 30 %, ambas vuelven al chip/barra de **porcentaje** normal.

### E. Referencias externas

- [ ] Feed `/marketplace`, sección "Referencias externas": cada tarjeta muestra el copy
      **exacto** "Referencia externa · datos no verificados" + el nombre de la fuente aparte.
- [ ] La tarjeta sigue siendo un **enlace vivo** al anuncio original (abre en pestaña nueva).
- [ ] `/marketplace/mis-referencias`: la misma etiqueta aparece en cada referencia propia.
- [ ] El **formulario de referenciar no cambió** (sigue reducido).

**Hallazgos del guión v2:**
- (anotar aquí)

## 4. De la versión test a productivo F1 (cuando el guión pase limpio)

1. **Cerrar compuerta M2** en `plan_market_autos.md` + entrada en bitácora con los hallazgos.
2. **Commit/push** de todo lo pendiente (incluida la deuda vieja de skills/docs).
3. **Render**: upgrade a **Starter ($7)** + cargar `CLOUDINARY_*` en el dashboard → deploy.
4. **Vercel**: deploy del frontend (sigue Hobby hasta la primera venta; Pro $20 al monetizar).
5. **UptimeRobot** apuntado a `/health` (ya debería estar; verificar).
6. **Dominio** `.com` (~$12/año) apuntado a Vercel — confianza del comprador.
7. Smoke test del guión §3 **sobre las URLs productivas** (más corto: 1 publicación completa).
8. Recién ahí: **M3 (filtros/búsqueda)** con datos reales de la prueba como semilla.

> Lo que NO necesita la F1: proveedor vehicular real (sigue mock hasta tener API key),
> pasarela de pagos (los tokens de cortesía bastan para validar), worker en la nube
> (tu PC alcanza), chat interno (M5 valida antes con WhatsApp).
