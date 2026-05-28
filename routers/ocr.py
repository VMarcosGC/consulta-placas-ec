"""Fase 5 — consulta por foto.

Recibe una imagen del vehículo, extrae la placa con OCR (Cloud Vision) y encadena
el resultado con la lógica de `GET /consultar/{placa}`.

Endpoint público (sin auth), igual que el resto de consultas a fuentes externas.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from database import obtener_sesion
from services.vision import extraer_placa_de_imagen


router = APIRouter(tags=["ocr"])

# Tope defensivo: una foto de placa no necesita más. Evita cargar imágenes enormes en RAM.
MAX_BYTES_IMAGEN = 8 * 1024 * 1024  # 8 MB

MENSAJE_SIN_PLACA = "No se detectó una placa ecuatoriana válida en la imagen"


@router.post("/consultar-foto")
async def consultar_foto(
    foto: UploadFile = File(...),
    sesion: Session = Depends(obtener_sesion),
):
    if not (foto.content_type or "").startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe ser una imagen",
        )

    # Leer acotado a MAX+1: nunca cargamos más que el tope en memoria, aunque el
    # cliente envíe un archivo enorme. Si llega al límite+1, lo rechazamos.
    imagen = await foto.read(MAX_BYTES_IMAGEN + 1)
    if not imagen:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=MENSAJE_SIN_PLACA,
        )
    if len(imagen) > MAX_BYTES_IMAGEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La imagen supera el tamaño máximo permitido (8 MB)",
        )

    resultado_ocr = await extraer_placa_de_imagen(imagen)
    estado = resultado_ocr.get("estado")

    if estado == "no_configurado":
        # Falta GOOGLE_VISION_API_KEY: es un fallo de despliegue, no de lectura.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de OCR no está configurado",
        )

    if estado != "placa_detectada":
        # sin_placa o error técnico → 400, nunca 500 (requisito de Fase 5).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=MENSAJE_SIN_PLACA,
        )

    placa = resultado_ocr["placa"]

    # Import diferido para evitar import circular: main importa este router al
    # cargar; aquí main ya está completamente inicializado en tiempo de request.
    from main import consultar_placa

    consulta = await consultar_placa(placa, sesion)
    return {"placa_detectada": placa, "consulta": consulta}
