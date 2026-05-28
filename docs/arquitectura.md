# Arquitectura — `consulta_placas_ec`

Diagramas Mermaid que reflejan el estado actual del sistema. Se actualizan a medida que avanzan los bloques. Renderizan en VSCode (preview de markdown), GitHub y GitLab sin tooling extra.

> **Convención**: lo que existe hoy va en color sólido; lo planeado va punteado con leyenda de fase.

---

## 1. Topología del sistema

Vista de alto nivel: actores, componentes y fuentes externas.

```mermaid
graph TD
    Usuario[Usuario]
    Web[Next.js<br/><i>Vercel free</i>]:::wip

    API[FastAPI<br/>main.py + routers/<br/><i>Render free</i>]
    Cache[(PostgreSQL<br/>Neon)]
    ANT[Servicio ANT<br/>services/ant.py]
    SRI[Servicio SRI<br/>services/sri.py<br/><i>bloqueado_captcha</i>]:::limitado
    AMT[Servicio AMT<br/>services/amt.py]
    FGE[Servicio Fiscalía<br/>services/fiscalia.py]

    ANTWeb[(consultaweb.ant.gob.ec)]
    SRIWeb[(srienlinea.sri.gob.ec)]
    AMTWeb[(servicios.axiscloud.ec<br/>portal AXIS - AMT)]
    FGEWeb[(gestiondefiscalias.gob.ec<br/>SIAF Noticias del Delito)]

    Usuario --> Web
    Usuario -->|/consultar/&#123;placa&#125; · ANT+SRI+AMT+FGE| API
    Usuario -->|/consultar-judicial/&#123;cedula&#125; · FGE| API
    Usuario -->|/auth/* · /vehiculos/* · duenos · kilometraje<br/>mantenimientos · /tokens · /favoritos · /compartir| API
    Usuario -->|/marketplace · /compartido/&#123;token&#125; · público| API
    Web -.->|fetch + JWT Bearer<br/>CORS| API

    API --> Cache
    API --> ANT
    API --> SRI
    API --> AMT
    API --> FGE

    ANT -->|Playwright| ANTWeb
    SRI -->|Playwright| SRIWeb
    AMT -->|Playwright| AMTWeb
    FGE -->|Playwright| FGEWeb

    classDef futuro stroke-dasharray: 5 5, stroke:#888;
    classDef wip stroke-dasharray: 5 5, stroke:#d97706, color:#d97706;
    classDef limitado stroke:#dc2626, color:#dc2626;
```

---

## 2a. Flujo de autenticación (Fase 2)

```mermaid
sequenceDiagram
    autonumber
    participant C as Cliente
    participant API as FastAPI
    participant Sec as auth/security.py
    participant DB as PostgreSQL

    Note over C,API: Registro
    C->>API: POST /auth/registro<br/>{email, password, nombre?}
    API->>Sec: hashear_password(password)
    Sec-->>API: bcrypt hash
    API->>DB: INSERT INTO usuarios (saldo_tokens=5)
    API->>DB: INSERT INTO transacciones_tokens<br/>(+5, "saldo_inicial")
    DB-->>API: usuario.id
    API-->>C: 201 {id, email, nombre, saldo_tokens, creado_en}

    Note over C,API: Login
    C->>API: POST /auth/login<br/>(form-data username/password)
    API->>DB: SELECT usuario WHERE email = ?
    DB-->>API: usuario + password_hash
    API->>Sec: verificar_password(plano, hash)
    alt password ok
        Sec-->>API: true
        API->>Sec: crear_token_acceso(sub=email)
        Sec-->>API: JWT firmado
        API-->>C: 200 {access_token, token_type: bearer}
    else password mal
        Sec-->>API: false
        API-->>C: 401 Email o password incorrectos
    end

    Note over C,API: Acceso autenticado
    C->>API: GET /auth/me<br/>Authorization: Bearer JWT
    API->>Sec: decodificar_token(JWT)
    Sec-->>API: email del sub
    API->>DB: SELECT usuario WHERE email = ?
    DB-->>API: usuario
    API-->>C: 200 {id, email, nombre, creado_en}
```

---

## 2b. Flujo del endpoint `GET /consultar/{placa}`

Secuencia con el caché ya integrado.

```mermaid
sequenceDiagram
    autonumber
    participant C as Cliente
    participant API as FastAPI<br/>(main.py)
    participant V as validar_placa
    participant Cache as services/cache.py
    participant DB as PostgreSQL
    participant Fuente as Servicio<br/>(ANT/SRI/AMT/FGE)
    participant Externa as Fuente externa

    C->>API: GET /consultar/ABC1234
    API->>V: validar_placa("ABC1234")
    alt placa inválida
        V-->>API: ValueError
        API-->>C: 400 Bad Request
    else placa válida
        V-->>API: "ABC1234"
        loop por cada fuente (ANT, SRI, AMT, FGE)
            API->>Cache: obtener_consulta_reciente(placa, fuente, TTL)
            Cache->>DB: SELECT ... WHERE placa, fuente, creado_en >= now - TTL
            alt hay caché vigente
                DB-->>Cache: respuesta JSONB
                Cache-->>API: respuesta + _cache:true
            else sin caché o BD caída
                Cache-->>API: None / excepción (loggeada)
                API->>Fuente: await consultar_X(placa)
                Fuente->>Externa: scraping (Playwright)
                Externa-->>Fuente: HTML
                Fuente-->>API: {fuente, placa, estado, datos}
                API->>Cache: guardar_consulta(...)
                Note over Cache,DB: solo si estado ∈ {consulta_realizada, sin_resultados}
                Cache->>DB: INSERT INTO consultas
            end
        end
        API->>API: armar resumen (indicadores agregados)
        API-->>C: 200 OK<br/>{placa, ant, sri, amt, fge, resumen}
    end
```

---

## 3. Modelo de datos

Entidades existentes (Fases 1-2) y entidades planeadas (Fases 3-4).

```mermaid
erDiagram
    consultas {
        bigint id PK
        string placa
        string fuente
        string estado
        jsonb respuesta
        timestamptz creado_en
    }

    usuarios {
        bigint id PK
        string email UK
        string password_hash
        string nombre
        int saldo_tokens
        timestamptz creado_en
        timestamptz actualizado_en
    }

    transacciones_tokens {
        bigint id PK
        bigint usuario_id FK
        int monto
        string motivo
        timestamptz fecha
    }

    vehiculos {
        bigint id PK
        bigint usuario_id FK
        string placa
        string vin
        string numero_motor
        string numero_chasis
        string marca
        string modelo
        int anio
        string color
        string transmision
        string tipo_motor
        string ciudad_registro
        bool en_venta
        numeric precio_venta_usd
        string url_externa
        timestamptz creado_en
        timestamptz actualizado_en
        timestamptz eliminado_en
    }

    vehiculos_favoritos {
        bigint id PK
        bigint usuario_id FK
        string placa
        string nota
        timestamptz creado_en
    }

    duenos_historico {
        bigint id PK
        bigint vehiculo_id FK
        string cedula_dueno
        string nombre_dueno
        date desde
        date hasta
    }

    kilometraje_lecturas {
        bigint id PK
        bigint vehiculo_id FK
        int kilometros
        timestamptz fecha_lectura
        string nota
    }

    mantenimientos {
        bigint id PK
        bigint vehiculo_id FK
        string tipo
        date fecha
        int kilometraje_relacionado
        string taller
        numeric costo
        timestamptz creado_en
    }

    enlaces_compartidos {
        bigint id PK
        bigint vehiculo_id FK
        string token UK
        jsonb scope
        timestamptz creado_en
        timestamptz fecha_expiracion
    }

    usuarios ||--o{ vehiculos : tiene
    usuarios ||--o{ transacciones_tokens : audita
    usuarios ||--o{ vehiculos_favoritos : sigue
    vehiculos ||--o{ duenos_historico : registra
    vehiculos ||--o{ kilometraje_lecturas : acumula
    vehiculos ||--o{ mantenimientos : recibe
    vehiculos ||--o{ enlaces_compartidos : genera
```

**Estado**:
- `consultas` → existe (migración `0001`).
- `usuarios`, `vehiculos`, `duenos_historico`, `kilometraje_lecturas` → existen (migración `0002`, Fase 2 — Bloque 1).
- `vehiculos.numero_motor` y `vehiculos.numero_chasis` → agregados en migración `0003` con soporte de ofuscación (ver [utils/ofuscacion.py](../utils/ofuscacion.py)).
- `vehiculos.transmision/tipo_motor/ciudad_registro`, `usuarios.saldo_tokens` y `transacciones_tokens` → agregados en migración `0004` (Fase 3 — perfil + billetera).
- `vehiculos_favoritos` → migración `0005`; placa como `String` (no FK), única por usuario+placa.
- `mantenimientos` → migración `0006`; `fecha` y `kilometraje_relacionado` monotónicos.
- `vehiculos.en_venta/precio_venta_usd/url_externa` → migración `0007` (Fase 4 — Marketplace). Un auto se lista en `GET /marketplace` solo si `en_venta` y `precio_venta_usd > 0`.
- `enlaces_compartidos` → migración `0008` (Fase 4 — token de compra-venta). `token` único (UK), TTL ≤ 7 días vía `fecha_expiracion`, `scope` JSONB opt-in. `GET /compartido/{token}` devuelve `VehiculoSalidaCompartida` (ofuscado).
- El campo `vehiculos_favoritos.placa` no es FK a propósito (se puede seguir una placa inexistente).

---

## 4. Roadmap visual por bloques

```mermaid
flowchart LR
    subgraph F1["Fase 1 — Consultas estables + caché"]
        B1[Bloque 1<br/>Persistencia base<br/><b>✅</b>]
        B2[Bloque 2<br/>Integrar caché<br/><b>✅</b>]
        B3[Bloque 3<br/>AMT real<br/><b>✅</b>]
        B4[Bloque 4<br/>Fiscalía FGE<br/><b>✅</b>]
        B5[Bloque 5<br/>SRI<br/>bloqueado_captcha<br/>📌 limitación]
    end

    subgraph F2["Fase 2 — Auth + vehículos + deploy"]
        F2A[Bloque 1<br/>Modelos<br/><b>✅</b>]
        F2B[Bloque 2<br/>Auth JWT<br/><b>✅</b>]
        F2C[Bloque 3<br/>CRUD vehículos<br/>+ deploy Render<br/><b>✅</b>]
        F2D[Bloque 4<br/>Dueños + kilometraje<br/><b>✅</b>]
    end

    subgraph F3["Fase 3 — Billetera + Favoritos + Mantenimientos"]
        F3A[Billetera de tokens<br/>+ auditoría<br/><b>✅</b>]
        F3B[Favoritos<br/>por placa<br/><b>✅</b>]
        F3C[Mantenimientos<br/>monotónicos<br/><b>✅</b>]
    end

    subgraph F4["Fase 4 — Compra-venta"]
        F4A[enlaces_compartidos<br/>token privado<br/><b>✅</b>]
        F4B[Marketplace público<br/>en_venta + precio<br/><b>✅</b>]
    end

    subgraph F5["Fase 5"]
        F5A[OCR de placa<br/>desde foto]
    end

    subgraph F6["Fase 6"]
        F6A[App móvil + web]
    end

    B1 --> B2 --> B3 --> B4 --> B5 --> F2A --> F2B --> F2C --> F2D --> F3A --> F3B --> F3C --> F4A --> F4B --> F5A --> F6A

    classDef done fill:#dcfce7,stroke:#16a34a;
    classDef wip fill:#fef9c3,stroke:#ca8a04;
    classDef limitado fill:#fee2e2,stroke:#dc2626;
    class B1,B2,B3,B4,F2A,F2B,F2C,F2D,F3A,F3B,F3C,F4A,F4B done
    class B5 limitado
```

---

## Cómo actualizar este archivo

- Cada vez que cerremos un bloque, marco el nodo correspondiente como ✅ en el roadmap.
- Cuando se agregue una fuente, sumarla a la topología (1) y a la secuencia (2).
- Cuando se cree una entidad nueva, sumarla al ER (3).
- Si un diagrama crece mucho, dividirlo en sub-vistas en archivos `docs/arquitectura/<tema>.md`.
