# Estructura general del proyecto

Documento marco para implementar una plataforma de aprendizaje de idiomas con juegos por servicio y análisis de pronunciación.

## 1) Objetivo del sistema

- Juegos didácticos sin mecánicas desmotivadoras (sin vidas/puntuación punitiva).
- Actividades por idioma con política de calendario (ej. japonés entre semana, inglés fines de semana).
- Notificaciones configurables por idioma/día/hora.
- Pipeline de audio modular para transcripción, análisis y feedback pedagógico.

## 2) Tipos de actividades de juego

- Sustitución de palabras/estructuras.
- Rellenar huecos.
- Audio y pronunciación correcta.
- Emparejar símbolos (hiragana/katakana/romaji).
- Orden de palabras.

## 3) Arquitectura por servicios

- `game-content-service`
  - Banco de actividades por idioma y nivel.
- `policy-service`
  - Selección de idioma por reglas de calendario y preferencia del usuario.
  - Configuración editable de idioma por día de semana.
- `notification-service`
  - Reglas semanales por idioma (día/hora) para enviar recordatorios.
- `speech-service`
  - STT (ElevenLabs STT y/o Whisper en servidor).
- `audio-preprocess-service`
  - Normalización de audio (`ffmpeg`/`sox`), VAD y limpieza.
- `alignment-service`
  - Alineación audio-texto (`WhisperX` o `MFA`).
- `acoustic-analysis-service`
  - Extracción de métricas acústicas (`Parselmouth`, `librosa`).
- `feedback-service`
  - Reglas heurísticas y LLM opcional (ChatGPT API).
- `orchestrator-api`
  - Punto de entrada para frontend/app.

## 4) Flujo recomendado para actividad de pronunciación

1. El frontend solicita actividad a `game-content-service`.
2. `policy-service` determina idioma activo.
3. Usuario envía audio.
4. `audio-preprocess-service` limpia y normaliza.
5. `speech-service` genera transcripción.
6. `alignment-service` mapea tiempos por palabra/fonema.
7. `acoustic-analysis-service` calcula métricas (pitch, pausas, ritmo).
8. `feedback-service` devuelve correcciones y siguiente práctica.

## 5) Contrato de respuesta sugerido

```json
{
  "activity_type": "pronunciation_guided",
  "language": "ja",
  "expected_text": "おはようございます",
  "recognized_text": "おはよう ございます",
  "metrics": {
    "pronunciation_confidence": 0.82,
    "speech_rate_wpm": 94,
    "pause_ratio": 0.18,
    "pitch_stability": 0.76
  },
  "word_feedback": [
    {
      "word": "ございます",
      "issue": "pausa excesiva antes de la palabra",
      "hint": "Intenta unirla con la palabra anterior en una sola respiración."
    }
  ],
  "next_step": "Repite la frase 3 veces con ritmo continuo."
}
```

## 6) Herramientas y coste (resumen)

- `ffmpeg`, `sox`, `Whisper/faster-whisper`, `MFA`, `Parselmouth`, `librosa`: open-source (sin coste de licencia).
- Coste real: infraestructura (CPU/GPU), almacenamiento, mantenimiento, y LLM opcional por tokens.
- Para volúmenes bajos (ej. ~100 audios/mes), el coste suele ser bajo y escalable por etapas.

## 7) Fases de implementación

1. **Fase 1 (MVP):** STT + actividad de pronunciación + feedback básico.
2. **Fase 2:** alineación + métricas acústicas.
3. **Fase 3:** feedback pedagógico avanzado con LLM opcional.
4. **Fase 4:** ampliar a más juegos/idiomas con contenido separado por servicio.
