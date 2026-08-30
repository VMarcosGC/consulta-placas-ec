"""Importa a `publicaciones_referenciadas` los 20 SUV de la matriz de Facebook
Marketplace (Quito) que armó Codex el 2026-08-30.

**Qué hace.** Estos anuncios NO son nuestros: son links de Facebook Marketplace con los
datos que se veían/declaraban al 2026-08-30. Se cargan como REFERENCIAS EXTERNAS —el
mismo mecanismo que "pega un link" de la web (`routers/referencias.py`)— para dar
volumen al feed. No se raspa nada: los 20 registros están horneados abajo.

**Estado de moderación.** Por defecto entran `pendiente` (invariante §10.6: una
referencia la revisa un admin antes de que el feed la muestre). Con `--aprobar` entran
`aprobada` + `activa` y salen al feed de inmediato.

**Aportante.** `usuario_id` = la cuenta de `--aportante EMAIL` (default
`mrkitov@gmail.com`) para que aparezcan en su "Mis referencias" y las pueda editar,
pausar o borrar desde la web. Si ese email no está en `usuarios`, se insertan con
`usuario_id = NULL` (el modelo lo permite) y se avisa.

**Uso**

    python -m scripts.importar_referencias_fb                 # carga, entran pendiente
    python -m scripts.importar_referencias_fb --aprobar       # carga y publica en el feed
    python -m scripts.importar_referencias_fb --aportante otro@correo.com
    python -m scripts.importar_referencias_fb --borrar        # elimina SOLO estos 20 (por URL)

Idempotente: identifica cada anuncio por `url_externa` (UK). Reejecutar no duplica;
actualiza precio/km/foto/descripción/estado de los que ya existían.

**Conexión.** Explícita a Neon leyendo `DATABASE_URL` de `.env` (mismo criterio que
`scripts/seed_demo.py`). Escrituras por SQLAlchemy Core contra `Model.__table__`.
Aviso: las URLs de foto de `fbcdn.net` vienen firmadas y **caducan en pocos días**;
cuando expiren, la tarjeta cae al placeholder "Sin fotos" (no rompe nada).
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, delete, insert, select, update
from sqlalchemy.orm import Session, sessionmaker

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import src.registry  # noqa: E402,F401  (registra los modelos en Base.metadata)

from src.modules.auth.models import Usuario  # noqa: E402
from src.modules.marketplace.models import (  # noqa: E402
    EstadoModeracion,
    PublicacionReferenciada,
)

_T_USUARIO = Usuario.__table__
_T_REF = PublicacionReferenciada.__table__

EMAIL_APORTANTE_DEFAULT = "mrkitov@gmail.com"
FUENTE = "Facebook Marketplace"  # lo que `schemas._derivar_fuente` da para facebook.com


# ── Los 20 anuncios (matriz SUV Quito, Codex 2026-08-30) ────────────────────────
# (marca, modelo, anio, precio, km|None, ciudad, motor, transmision, traccion,
#  capacidad, caracteristicas, alertas, url, foto)
_ANUNCIOS: list[dict] = [
    dict(marca="SWM", modelo="G01 Dorado", anio=2024, precio=14000, km=95000,
         ciudad="Quito", motor="No indicado", transmision="No indicada",
         traccion="No indicada", capacidad="SUV familiar",
         caracteristicas="Papeles en regla; uso particular; mantenimientos declarados; precio conversable",
         alertas="Kilometraje elevado para el año; verificar versión, motor, caja e historial",
         url="https://www.facebook.com/marketplace/item/2149287785945796/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.84726-6/778755866_1900665907560439_5000952269047374152_n.jpg?stp=c0.43.261.261a_dst-jpg_p261x260_tt6&_nc_cat=103&ccb=1-7&_nc_sid=92e707&_nc_ohc=czgxDXzW1HkQ7kNvwEDUmSp&_nc_oc=Adq_Hd2j5kQHK1A7spoGwOudZOgY0JlR48lvyngCiWlcf2Z6xDx4UtR65wA5Wu0kEEJv3P8szhbE1SUyqfYYRLjs&_nc_zt=14&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQKp0KCJ0M9R8Q-_WwjjH1vZnMinb0G1xUaZxDz5PEV94Q&oe=6A99E585"),
    dict(marca="Haval", modelo="H6 Supreme", anio=2021, precio=17500, km=None,
         ciudad="Quito", motor="No indicado", transmision="No indicada",
         traccion="No indicada", capacidad="5 pasajeros aprox.",
         caracteristicas="Versión Supreme; cuero; techo panorámico; llantas recién cambiadas",
         alertas="No informa kilometraje, motor ni caja; solicitar historial y diagnóstico",
         url="https://www.facebook.com/marketplace/item/2203069830262433/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.30808-6/773450444_1397311585660515_6516676039776080007_n.jpg?stp=c350.0.900.900a_dst-jpg_tt6&cstp=mx900x900&ctp=s261x260&_nc_cat=100&ccb=1-7&_nc_sid=454cf4&_nc_ohc=Dvr8mZ_rNL8Q7kNvwEgkmkw&_nc_oc=AdrxaPhOLbYXYDZ5rwoaFlwQkNV_GCjt48oXuvA1X5MyMbmczc-EfH6OdojxvWPnGMurs64PpL50ecSo3vblT7oi&_nc_zt=23&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQLgp7E27G8YnZAq6jg6BLUpUf8HtLwg6KqqWGDD68lXkw&oe=6A9A1072"),
    dict(marca="Changan", modelo="CS15", anio=2024, precio=13300, km=35000,
         ciudad="Quito", motor="No indicado", transmision="No indicada",
         traccion="No indicada", capacidad="SUV compacto",
         caracteristicas="Bajo kilometraje declarado; unidad reciente; precio atractivo",
         alertas="Descripción muy corta; confirmar dueño, mantenimientos, siniestros y garantía",
         url="https://www.facebook.com/marketplace/item/3522435641296924/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.30808-6/785123838_28617546717933383_5836707662285139577_n.jpg?stp=c126.0.768.768a_dst-jpg_tt6&cstp=mx768x768&ctp=s261x260&_nc_cat=110&ccb=1-7&_nc_sid=454cf4&_nc_ohc=G1x4JBcz2sAQ7kNvwEO4Pbl&_nc_oc=AdoADor6DL_cN-kzQ2SBAxVcjFqoElHnaqdUoXa4LfnN9mRbSD42k3QEkp49EatYZbp-DrhNuLrTdvgk1NV5cdQ4&_nc_zt=23&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQKJu8hrgBlbNthQ3f-TMTQxQmms32xlnhSIFV2-bb0JPg&oe=6A99FE50"),
    dict(marca="Nissan", modelo="X-Trail Sense", anio=2015, precio=13500, km=200000,
         ciudad="Conocoto", motor="No indicado", transmision="Automática",
         traccion="No indicada", capacidad="3 filas",
         caracteristicas="Dos dueños; RTV Quito; matrícula 2025; tres filas",
         alertas="Kilometraje alto; revisar caja CVT, suspensión y trazabilidad del mantenimiento",
         url="https://www.facebook.com/marketplace/item/1074169005184131/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.30808-6/787639454_10234984447096558_8579137353976770299_n.jpg?stp=c0.436.1080.1080a_dst-jpg_tt6&cstp=mx1080x1080&ctp=s261x260&_nc_cat=105&ccb=1-7&_nc_sid=454cf4&_nc_ohc=5UI4SGHefKQQ7kNvwG3ZXZw&_nc_oc=AdojmHTIkt9A4dzNU1h9MMt2_1uwJD2fqgVXs2F0q5--dLKJumCPU5LXuQGiO39xrI45iI_7z5kG4y1FLU2duEml&_nc_zt=23&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQKRYZ0y8Md_3B-hLUJOgaaeOzZZS4TI5CZiPlrViuPPXQ&oe=6A99DFB4"),
    dict(marca="Kia", modelo="Niro Hybrid", anio=2017, precio=13500, km=156660,
         ciudad="Nayón", motor="Híbrido gasolina-eléctrico", transmision="Automática",
         traccion="No indicada", capacidad="5 pasajeros",
         caracteristicas="Versión full; sensores; multimedia; crucero; dos llaves y manuales",
         alertas="Exigir diagnóstico de batería híbrida y comprobación de historial/siniestros",
         url="https://www.facebook.com/marketplace/item/1549778799604257/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.30808-6/787036588_10244747448200409_1227909401812272313_n.jpg?stp=c125.0.750.750a_dst-jpg_tt6&cstp=mx750x750&ctp=s261x260&_nc_cat=105&ccb=1-7&_nc_sid=454cf4&_nc_ohc=s0My9fNB308Q7kNvwGbFJuq&_nc_oc=AdpqtsQW7KDlfp9ON2RDGI2vhbNVKkuIU1sGCMqknK9RDSjq-4cF-5d9A0gjCOTbRiTYedTCSnrZbgDcf9yT8P_b&_nc_zt=23&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQI82i6NdxldNb7EOlM-P5ItEa3zAo9tACpNa8pBhs1Eiw&oe=6A99FAE3"),
    dict(marca="Nissan", modelo="Qashqai 2.0 CVT", anio=2012, precio=13500, km=160000,
         ciudad="Quito", motor="2.0 gasolina", transmision="CVT automática",
         traccion="4x2", capacidad="5 pasajeros",
         caracteristicas="Cuero; climatizador bizona; crucero; mantenimientos declarados en casa comercial",
         alertas="Revisar rigurosamente CVT, soportes, suspensión y kilometraje",
         url="https://www.facebook.com/marketplace/item/1417908406870851/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.30808-6/781251245_2523774411430013_6508083452480657538_n.jpg?stp=c308.0.665.665a_dst-jpg_tt6&cstp=mx665x665&ctp=s261x260&_nc_cat=111&ccb=1-7&_nc_sid=454cf4&_nc_ohc=qmnbnSuSgrcQ7kNvwHkkXIN&_nc_oc=AdrjY14GB_QtQonRb_ObEtjKddpLn_R3set-3VCmkmze0CN8Z9Y-T8B-RMvGPt37dCNn94Nwo3qHss2Hkj3P1YId&_nc_zt=23&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQKZ4cQ9PEHRzRyONimeEcYXhFcLa1xNLHKGdm53YeXpxA&oe=6A99E69F"),
    dict(marca="DFSK", modelo="Glory 560", anio=2022, precio=13900, km=149000,
         ciudad="Quito", motor="1.8 gasolina", transmision="Manual",
         traccion="No indicada", capacidad="3 filas",
         caracteristicas="Cámara; sensores; pantalla; matrícula al día; precio negociable",
         alertas="Kilometraje muy alto para el año; posible uso intensivo",
         url="https://www.facebook.com/marketplace/item/1728581115086273/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.30808-6/786303870_10234219746907001_5205505406861918846_n.jpg?stp=c0.107.1080.1080a_dst-jpg_tt6&cstp=mx1080x1080&ctp=s261x260&_nc_cat=100&ccb=1-7&_nc_sid=454cf4&_nc_ohc=79N1xXAC7-YQ7kNvwFy_gF2&_nc_oc=AdrfhaMgMWZojdE94_CzQHAh0fDMgemFz8c6kb9YCpTVRyI79claQlS2PAcU-42DcC96QdUAiibdfdtrwaXzKZT3&_nc_zt=23&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQJ8pSQPmFBamzjnn-wyzXiwZTZO-pZo9L1NYRfOv-RADQ&oe=6A99E054"),
    dict(marca="Renault", modelo="Duster", anio=2023, precio=17900, km=75622,
         ciudad="Quito", motor="1.3 gasolina", transmision="Automática",
         traccion="4x2", capacidad="5 pasajeros",
         caracteristicas="Unidad reciente; kilometraje razonable; configuración urbana",
         alertas="Precio en techo del rango; verificar versión, turbo, caja e historial",
         url="https://www.facebook.com/marketplace/item/1362961076004923/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.84726-6/780374903_2964588903905452_8161399354607467112_n.jpg?stp=c43.0.260.260a_dst-jpg_p261x260_tt6&_nc_cat=106&ccb=1-7&_nc_sid=92e707&_nc_ohc=uN8OJ0W-NV0Q7kNvwHSM7vw&_nc_oc=AdptvIAXnizd5Z3ilzBtlwSr2qntabPXPVHGOpofLbbfFuXPDk6zE27wmms6UvtvJOwpozwOa4sKhKiAwDxK1DYU&_nc_zt=14&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQL2ucXJHEAjhwc-cJ3STbRo86jLApr5M4kjNb6_4I0EBQ&oe=6A99DD55"),
    dict(marca="SWM", modelo="G01", anio=2025, precio=15800, km=33000,
         ciudad="Quito", motor="No indicado", transmision="No indicada",
         traccion="No indicada", capacidad="SUV familiar",
         caracteristicas="Único dueño; bajo kilometraje; firma directa en notaría; full equipo declarado",
         alertas="Confirmar especificación, garantía vigente, mantenimientos y origen",
         url="https://www.facebook.com/marketplace/item/1599019658477209/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.84726-6/790227137_2465405127292687_809763126558177512_n.jpg?stp=c43.0.260.260a_dst-jpg_p261x260_tt6&_nc_cat=105&ccb=1-7&_nc_sid=92e707&_nc_ohc=bPU60NNNdpcQ7kNvwHJa6gV&_nc_oc=AdppaT3clq2_khQWymdkVlUDgNlIhjWCaHNEpq90D274gElvBMK3IDDqLUDGnZTF4y01j3oH6NSBN46sOa-WhBte&_nc_zt=14&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQLRAI4KuLj696RhCdk-6N8GeRlRs00WH-XdkFHUKCA0ag&oe=6A99DE96"),
    dict(marca="Shineray", modelo="G03", anio=2024, precio=13500, km=None,
         ciudad="Quito", motor="1.5 gasolina", transmision="Manual",
         traccion="No indicada", capacidad="3 filas",
         caracteristicas="Cuero; aire acondicionado; tres filas; precio negociable",
         alertas="No informa kilometraje; anuncio antiguo; confirmar disponibilidad y seguridad",
         url="https://www.facebook.com/marketplace/item/1385151303682093/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.84726-6/744074866_1055197480407180_7004572786510126124_n.jpg?stp=c43.0.260.260a_dst-jpg_p261x260_tt6&_nc_cat=110&ccb=1-7&_nc_sid=92e707&_nc_ohc=6mCNMia8JGUQ7kNvwEtgKwj&_nc_oc=AdotEaaP9YlpOM9I-RKYqQvvSKxfU6N9sEDXHQlHuWgREgl-jGjn0Rp9NvCa8jO_QpvwMeLYB_2xAVsKv3KmceXF&_nc_zt=14&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQKLrs3QBV8-iHXAwE0Z4xyCfc1bhbl-rwnimNIPLHgraQ&oe=6A99E569"),
    dict(marca="Lexus", modelo="RX 450h", anio=2010, precio=17500, km=None,
         ciudad="Mindo", motor="3.5 V6 híbrido", transmision="Automática",
         traccion="No indicada", capacidad="5 pasajeros",
         caracteristicas="Cuero; climatizador dual; cámara; sunroof; mantenimiento declarado",
         alertas="No informa km; batería híbrida, suspensión y repuestos premium pueden ser costosos",
         url="https://www.facebook.com/marketplace/item/1878275813336887/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.84726-6/763103506_1038912755209664_7171246940061548833_n.jpg?stp=c0.43.261.261a_dst-jpg_p261x260_tt6&_nc_cat=107&ccb=1-7&_nc_sid=92e707&_nc_ohc=6ysdfhGCAUgQ7kNvwEmIXZu&_nc_oc=AdqhSioKeitTAHWGIxY9isHaAeicSWrraZHSWVj7P299zQLcbgsojjfzDOXhbWN_hKgzNlVUyDsBaPbpwY--s187&_nc_zt=14&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQJsqzSCy90hV9oARvR2h-WxGkvKDa4CQaAHYuVah6bFhg&oe=6A99FF93"),
    dict(marca="Chevrolet", modelo="Captiva Premier", anio=2022, precio=15900, km=69000,
         ciudad="Quito", motor="1.5 turbo", transmision="Automática",
         traccion="No indicada", capacidad="3 filas",
         caracteristicas="Único dueño; cuero; sunroof; CarPlay/Android Auto; mantenimientos Chevrolet",
         alertas="Confirmar historial de caja/turbo, campaña técnica, choques y kilometraje",
         url="https://www.facebook.com/marketplace/item/946384801104129/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.84726-6/782144986_1536638854451029_7261742625018099392_n.jpg?stp=c43.0.260.260a_dst-jpg_p261x260_tt6&_nc_cat=107&ccb=1-7&_nc_sid=92e707&_nc_ohc=moA1YTk8heQQ7kNvwGWzzhP&_nc_oc=Ado2wswRMSPEo3SXq2clKUUVDVTLwXSqc1Kl-TaHHnUJDz9toycwBOjLGTlIte20YnehFe2bfSSobp8vQ4kS4T-J&_nc_zt=14&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQL9TYFBcx4i4RXVygYA11yUjoS8p3Nw6BykxOpZy4GptA&oe=6A9A06DF"),
    dict(marca="Chery", modelo="Tiggo 7 Pro", anio=2024, precio=17590, km=None,
         ciudad="Quito", motor="1.5 turbo", transmision="Manual",
         traccion="No indicada", capacidad="5 pasajeros",
         caracteristicas="Cuero; cámara y sensores; control de estabilidad; documentos declarados listos",
         alertas="No informa km; publicación de 25 semanas; confirmar disponibilidad y precio real",
         url="https://www.facebook.com/marketplace/item/990675040576281/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.84726-6/647299567_1891467318206085_4282879576408939999_n.jpg?stp=c43.0.260.260a_dst-jpg_p261x260_tt6&_nc_cat=107&ccb=1-7&_nc_sid=92e707&_nc_ohc=RpXudN0RURAQ7kNvwGZwriF&_nc_oc=Adptws8hFPYz4s5G1kpmBszP2RJ3Qhdvu1cM1F-NWtFMTyP6ci3IAIQkxxyd982BmQhiAXpqkIdHWjqE4dfc5LEB&_nc_zt=14&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQLu0hJvuMOvESqW_EseIzo9VUs2P2xGLKXb_uIGg7s2dg&oe=6A9A0BAC"),
    dict(marca="Nissan", modelo="Pathfinder 4.0", anio=2007, precio=14400, km=183000,
         ciudad="Quito", motor="4.0 gasolina", transmision="Automática",
         traccion="No indicada", capacidad="SUV grande",
         caracteristicas="Amplia; potente; financiación ofrecida",
         alertas="Consumo alto; antigüedad; confirmar 4x4, enfriamiento, caja y procedencia",
         url="https://www.facebook.com/marketplace/item/1621049939355891/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.30808-6/788831078_4074729592820099_3793479214551867853_n.jpg?stp=c160.0.960.960a_dst-jpg_tt6&cstp=mx960x960&ctp=s261x260&_nc_cat=105&ccb=1-7&_nc_sid=454cf4&_nc_ohc=lV9CoR8scY4Q7kNvwHJYtsC&_nc_oc=AdpUOeRVahuJqq2gMPawoVPGf7fDlkc0Ipj7hY3ZlwVzLVwjgdYb6nufz43myG7Rdm0Cb-b86dKBAi7A1UTGZ6Fz&_nc_zt=23&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQIGPjIfDRY4ksbgm-vE2Ocf_VOBnYqbYaVcVZ9zCvHbkg&oe=6A99EB3C"),
    dict(marca="Hyundai", modelo="Santa Fe 2.4", anio=2015, precio=17500, km=198280,
         ciudad="Quito", motor="2.4 gasolina", transmision="Automática Tiptronic",
         traccion="4x2", capacidad="5 pasajeros",
         caracteristicas="CarPlay; radio original incluido; papeles al día; precio negociable",
         alertas="Kilometraje alto y precio elevado; revisar motor, caja y consumo de aceite",
         url="https://www.facebook.com/marketplace/item/1601441384868070/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.84726-6/784774809_1067312222870115_5168805426321629476_n.jpg?stp=c0.0.261.261a_dst-jpg_p261x260_tt6&_nc_cat=105&ccb=1-7&_nc_sid=92e707&_nc_ohc=4XORVKbHQdQQ7kNvwGjeoYm&_nc_oc=AdrOOn40gPDfAUZeAlPhncnVbCVpo8Ko_S9V_NFkLg4EB9Y-jX3fMEypSBfwlUqy7MKRVVNtvLS4g_qdix7dj47c&_nc_zt=14&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQIw9UJ9sxYiXD9XCSdD_2Q0BhHSCEE8D8XL6g4KfzjBRw&oe=6A99FD23"),
    dict(marca="Ford", modelo="Edge 3.5 SE", anio=2013, precio=14900, km=149000,
         ciudad="Quito", motor="3.5 V6 gasolina", transmision="Automática",
         traccion="4x2", capacidad="5 pasajeros",
         caracteristicas="Matrícula/RTV 2026; segunda llave; algunos mantenimientos en Quito Motors",
         alertas="Importado de Canadá: verificar historial, corrosión, siniestros y consumo",
         url="https://www.facebook.com/marketplace/item/1392776955629283/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.84726-6/756227124_4462993593969688_3370830011243978729_n.jpg?stp=c43.0.260.260a_dst-jpg_p261x260_tt6&_nc_cat=102&ccb=1-7&_nc_sid=92e707&_nc_ohc=U__GiF750YgQ7kNvwEeI6Ck&_nc_oc=AdpzG1TnO8-qoOQ8YpEGVdiK_LjmjHOh5tPcV9cR7a5MU0PADYcNbFW41EsiYSBT8EIL-cAfXcmAtNE4GwX40dTI&_nc_zt=14&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQKYSetLHpJ4a3CDdszBgx-95xEeOf-SPWCMbwszfaxabg&oe=6A9A0370"),
    dict(marca="Chery", modelo="Tiggo 8", anio=2022, precio=16000, km=78000,
         ciudad="Sangolquí", motor="2.0 turbo (según vendedor)", transmision="Automática",
         traccion="No indicada", capacidad="7 pasajeros",
         caracteristicas="Único dueño; 3 filas; CarPlay; climatizador; asistentes declarados",
         alertas="Confirmar versión/motor exactos, caja, turbo y funcionamiento de ayudas",
         url="https://www.facebook.com/marketplace/item/1585037519932786/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.84726-6/787405808_2070199023864770_5025823703709674371_n.jpg?stp=c43.0.260.260a_dst-jpg_p261x260_tt6&_nc_cat=101&ccb=1-7&_nc_sid=92e707&_nc_ohc=UanWmFWgb5UQ7kNvwE8Stso&_nc_oc=AdorkoWeuT00y-pkukBDyvFd4ZFXOb3TshuOlrTsHC7F7Ix1-453YqvxKhauSo0b-3pTVSM8Rk8o8wjyG8ABnM6q&_nc_zt=14&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQLtSuMr7nsa3vIG2hM2UR42rAqq41adM7K4h0XFIbrz6Q&oe=6A99EE99"),
    dict(marca="Dongfeng", modelo="SX5 2.0", anio=2022, precio=14500, km=73153,
         ciudad="Quito", motor="2.0 gasolina", transmision="Manual 5 vel.",
         traccion="4x2", capacidad="5 pasajeros",
         caracteristicas="RTV/matrícula al día; batería nueva; acepta revisión; vendedor declara raspón",
         alertas="Inspeccionar golpe posterior, embrague y validar kilometraje/documentos",
         url="https://www.facebook.com/marketplace/item/2113471773381284/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.30808-6/786629856_999638533121455_5649441280570449056_n.jpg?stp=c0.116.869.869a_dst-jpg_tt6&cstp=mx869x869&ctp=s261x260&_nc_cat=106&ccb=1-7&_nc_sid=454cf4&_nc_ohc=_tqxuFbk5iQQ7kNvwEHvQ4o&_nc_oc=AdqJT-fbnyFijvRD0P4BxslU1XcV_uUop-WcTCS8W14frA3f22uOgAoFICvBWR-TxpX0dWup0NrZ4znB-1Js5s_5&_nc_zt=23&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQLxKkNbgWdXccOrVYWsgeFm-rcnd44Y47Mzss-7AbP03g&oe=6A9A03D5"),
    dict(marca="Chevrolet", modelo="Tracker Turbo LS", anio=2021, precio=16800, km=105000,
         ciudad="Quito", motor="1.2 turbo", transmision="Manual",
         traccion="No indicada", capacidad="5 pasajeros",
         caracteristicas="Único dueño; OnStar; CarPlay/Android Auto; cámara y controles de estabilidad",
         alertas="Kilometraje alto; revisar turbo, embrague, mantenimientos y transferencia segura",
         url="https://www.facebook.com/marketplace/item/2539132126547675/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.84726-6/734522028_1544068100458809_3249069848447522908_n.jpg?stp=c64.0.260.260a_dst-jpg_p261x260_tt6&_nc_cat=106&ccb=1-7&_nc_sid=92e707&_nc_ohc=xl8-eZxJwU4Q7kNvwFHMUcZ&_nc_oc=AdpEgMsf0bSJF5RPlcuA60J13hCgcnblF7jGzzEBUZuBmtD74kSnm-YSoc1rq5poe5e0ciQ_dxrPHC_aJXNvPgul&_nc_zt=14&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQKODRGVw0VLrbKWK17VBx8VSlxuHmLL-RK8N_VsV3aymw&oe=6A99FD66"),
    dict(marca="Chevrolet", modelo="Tracker Premier", anio=2024, precio=14500, km=None,
         ciudad="Quito", motor="No indicado", transmision="No indicada",
         traccion="No indicada", capacidad="SUV compacto",
         caracteristicas="Versión Premier declarada; precio llamativo; acepta tarjeta",
         alertas="Muy poca información y precio inusualmente bajo; confirmar km, propiedad y condiciones",
         url="https://www.facebook.com/marketplace/item/1410334164606407/",
         foto="https://scontent.fuio21-1.fna.fbcdn.net/v/t39.30808-6/788261435_122129734161379707_474797983541853337_n.jpg?stp=c267.0.546.546a_dst-jpg_tt6&cstp=mx546x546&ctp=s261x260&_nc_cat=111&ccb=1-7&_nc_sid=454cf4&_nc_ohc=gn366slA7kgQ7kNvwFhr2ri&_nc_oc=AdpCji7s5XOfZE7IfLLjOyZ4xKvwSihWHO-n6UKeafD62wPGBZVn4cIgmz-ln8z9X3c0yo9SyBCnziMWUbLmwVKH&_nc_zt=23&_nc_ht=scontent.fuio21-1.fna&_nc_gid=eSTD8wsN3ypAPerFZ_Ssng&_nc_ss=7b289&oh=00_AQIY7mtGn4xUJjXWoLnOcyANu92eljZ_7gaxHAer81vN1g&oe=6A9A0312"),
]

_MAX_DESC = 2000
_NO_INDICA = {"no indicado", "no indicada", "", None}


def _descripcion(a: dict) -> str:
    tecnica = " · ".join(
        v for v in (a["motor"], a["transmision"], a["traccion"], a["capacidad"])
        if (v or "").strip().lower() not in _NO_INDICA
    )
    partes = [a["caracteristicas"]]
    if tecnica:
        partes.append(tecnica)
    partes.append(f"A revisar: {a['alertas']}")
    partes.append(
        "Comparativa de SUV en Quito (2026-08-30) · datos declarados por el vendedor "
        "en Facebook Marketplace, no verificados por la plataforma."
    )
    return "\n".join(partes)[:_MAX_DESC]


def _fila(a: dict, usuario_id: int | None, estado: str) -> dict:
    foto = (a.get("foto") or "").strip() or None
    return dict(
        usuario_id=usuario_id,
        vendedor_id=None,
        url_externa=a["url"],
        fuente=FUENTE,
        marca=a["marca"][:80],
        modelo=a["modelo"][:120],
        anio=a["anio"],
        precio_usd=Decimal(str(a["precio"])),
        imagen_url=foto,
        placa=None,
        descripcion=_descripcion(a),
        ciudad=a["ciudad"][:80],
        kilometraje=a["km"],
        fotos=[foto] if foto else [],
        estado_moderacion=estado,
        activa=True,
    )


# ── Conexión a Neon (idéntico criterio que scripts/seed_demo.py) ────────────────

def _dsn_neon() -> str:
    valores = dotenv_values(RAIZ / ".env")
    crudo = (valores.get("DATABASE_URL") or "").strip()
    if not crudo:
        print("ERROR: `.env` no tiene DATABASE_URL.")
        raise SystemExit(2)
    if crudo.startswith("postgresql+"):
        return crudo
    if crudo.startswith("postgresql://"):
        return "postgresql+psycopg://" + crudo[len("postgresql://"):]
    if crudo.startswith("postgres://"):
        return "postgresql+psycopg://" + crudo[len("postgres://"):]
    return crudo


def _abrir_sesion() -> tuple[Session, object]:
    engine = create_engine(_dsn_neon(), pool_pre_ping=True, future=True)
    fabrica = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return fabrica(), engine


def _usuario_id(sesion: Session, email: str) -> int | None:
    fila = sesion.execute(
        select(_T_USUARIO.c.id).where(_T_USUARIO.c.email == email)
    ).first()
    return fila[0] if fila else None


# ── Operaciones ────────────────────────────────────────────────────────────────

def importar(sesion: Session, email: str, aprobar: bool) -> dict:
    estado = (
        EstadoModeracion.APROBADA.value if aprobar else EstadoModeracion.PENDIENTE.value
    )
    uid = _usuario_id(sesion, email)
    if uid is None:
        print(f"  AVISO: no existe la cuenta '{email}'. Se cargan con usuario_id=NULL "
              f"(no aparecerán en 'Mis referencias' de nadie).")

    urls = [a["url"] for a in _ANUNCIOS]
    existentes = {
        u for (u,) in sesion.execute(
            select(_T_REF.c.url_externa).where(_T_REF.c.url_externa.in_(urls))
        )
    }

    creadas = actualizadas = 0
    for a in _ANUNCIOS:
        fila = _fila(a, uid, estado)
        if a["url"] in existentes:
            # Refresca lo que pudo cambiar; respeta un usuario_id ya asignado a mano.
            sesion.execute(
                update(_T_REF)
                .where(_T_REF.c.url_externa == a["url"])
                .values(
                    precio_usd=fila["precio_usd"],
                    kilometraje=fila["kilometraje"],
                    imagen_url=fila["imagen_url"],
                    fotos=fila["fotos"],
                    descripcion=fila["descripcion"],
                    ciudad=fila["ciudad"],
                    estado_moderacion=fila["estado_moderacion"],
                    activa=True,
                )
            )
            actualizadas += 1
        else:
            sesion.execute(insert(_T_REF).values(**fila))
            creadas += 1

    sesion.commit()
    return {"creadas": creadas, "actualizadas": actualizadas, "estado": estado, "uid": uid}


def borrar(sesion: Session) -> int:
    urls = [a["url"] for a in _ANUNCIOS]
    n = sesion.execute(
        delete(_T_REF).where(_T_REF.c.url_externa.in_(urls))
    ).rowcount
    sesion.commit()
    return n


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    args = argv[1:]
    modo_borrar = "--borrar" in args
    aprobar = "--aprobar" in args
    email = EMAIL_APORTANTE_DEFAULT
    if "--aportante" in args:
        i = args.index("--aportante")
        if i + 1 < len(args):
            email = args[i + 1]

    desconocidos = set(args) - {"--borrar", "--aprobar", "--aportante", email}
    if desconocidos:
        print(__doc__)
        return 2

    sesion, engine = _abrir_sesion()
    try:
        print("=" * 64)
        print("  IMPORTAR REFERENCIAS FB — SUV Quito (matriz 2026-08-30)")
        print("=" * 64)
        if modo_borrar:
            n = borrar(sesion)
            print(f"\n  Eliminadas {n} referencias (por url_externa).")
            return 0
        r = importar(sesion, email, aprobar)
        print(f"\n  Aportante:  {email} (usuario_id={r['uid']})")
        print(f"  Estado:     {r['estado']}"
              + ("  → visibles en el feed" if aprobar else "  → a revisar en /admin/moderacion"))
        print(f"  Creadas:    {r['creadas']}")
        print(f"  Actualizadas: {r['actualizadas']}")
        print(f"  Total:      {r['creadas'] + r['actualizadas']} / {len(_ANUNCIOS)}")
        if not aprobar:
            print("\n  Para publicarlas: repetir con --aprobar, o aprobarlas una por una")
            print("  en /admin/moderacion.")
        print("\n  Deshacer: python -m scripts.importar_referencias_fb --borrar")
        return 0
    finally:
        sesion.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
