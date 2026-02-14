# Estimación rápida de coste para 100 audios/mes

> Referencia orientativa (puede variar por región, fecha y tipo de modelo). Confirmar siempre en la calculadora oficial del proveedor antes de contratar.

## Supuestos

- Volumen: **100 audios/mes**.
- Duración media de cada audio (3 escenarios):
  - Escenario A: 15 segundos
  - Escenario B: 30 segundos
  - Escenario C: 60 segundos
- Minutos mensuales resultantes:
  - A: 25 min/mes
  - B: 50 min/mes
  - C: 100 min/mes

## Rangos de precio típicos (STT en la nube)

- Rango habitual por minuto: **USD 0.016–0.024 / min**
  - (aprox. equivalente a proveedores conocidos como Google/AWS en planes estándar).

## Estimación de coste mensual

| Escenario | Minutos/mes | Precio bajo (0.016/min) | Precio alto (0.024/min) |
|---|---:|---:|---:|
| A (15s x 100) | 25 | USD 0.40 | USD 0.60 |
| B (30s x 100) | 50 | USD 0.80 | USD 1.20 |
| C (60s x 100) | 100 | USD 1.60 | USD 2.40 |

## Opciones gratuitas (open-source) y facilidad de uso/configuración

Estas opciones no cobran por API, pero sí requieren infraestructura (tu servidor/CPU/GPU) y algo de integración técnica.

| Opción | Para qué sirve | Coste licencia | Facilidad de uso | Facilidad de integración en el proyecto |
|---|---|---|---|---|
| `faster-whisper` | Transcribir audio a texto (STT) | Gratis | **Alta** | **Alta** |
| `WhisperX` | Transcripción + tiempos por palabra (alineación) | Gratis | Media | Media |
| `Montreal Forced Aligner (MFA)` | Alineación forzada de audio-texto más lingüística | Gratis | Media-baja | Media-baja |
| `Parselmouth` + `Praat` | Análisis de pitch, duración y rasgos de pronunciación | Gratis | Media | Media |
| `librosa` | Extracción de features de audio para scoring propio | Gratis | Media | Alta |

### Recomendación por facilidad (de más simple a más avanzada)

1. **`faster-whisper` (MVP rápido):**
   - Muy buena primera opción para arrancar.
   - Se integra bien como microservicio de transcripción.
2. **`WhisperX` (cuando necesites feedback por palabra):**
   - Añade timestamps útiles para ejercicios tipo huecos, orden y pronunciación guiada.
3. **`Parselmouth/Praat` y `librosa` (mejora de calidad):**
   - Útil para feedback más detallado (entonación/ritmo).
4. **`MFA` (nivel más experto):**
   - Más setup, pero potencia análisis fonético más fino.

## Integración sugerida dentro de vuestro proyecto

Dado vuestro enfoque de juegos por servicio (sustitución, huecos, audio/pronunciación, emparejar símbolos japoneses, orden de palabras), una estructura mínima y simple sería:

- `game-content-service`
  - Devuelve actividades por idioma (JA/EN) y tipo de juego.
- `speech-service`
  - Endpoint `POST /transcribe` (usa `faster-whisper`).
  - Endpoint `POST /pronunciation-feedback` (inicio: reglas básicas con texto esperado + timings).
- `policy-service`
  - Regla por calendario (ej. japonés entre semana, inglés fin de semana).
- `orchestrator-api`
  - Une todo para frontend/app.

### Orden recomendado de implementación (rápido y con bajo riesgo)

1. Implementar `speech-service` con `faster-whisper`.
2. Añadir `WhisperX` para tiempos por palabra.
3. Añadir features de `Parselmouth/librosa` para feedback más pedagógico.
4. Solo si hace falta precisión fonética avanzada, incorporar `MFA`.

## Si ya tienes ElevenLabs STT + Whisper en Home Assistant

Si ya dispones de STT en ambos lados, la transcripción base está cubierta. Para análisis de pronunciación y calidad de audio, os faltaría principalmente esta capa:

1. **Normalización y limpieza de audio**
   - Herramientas: `ffmpeg`, `sox`, `webrtcvad`.
   - Objetivo: quitar silencios largos, unificar sample rate (p. ej. 16 kHz), detectar voz/no voz.
2. **Alineación palabra/fonema con texto esperado**
   - Herramientas: `WhisperX` (rápido) o `MFA` (más preciso lingüísticamente).
   - Objetivo: saber exactamente qué parte del audio corresponde a cada palabra/fonema.
3. **Extracción de rasgos acústicos de pronunciación**
   - Herramientas: `Parselmouth/Praat`, `librosa`, opcional `openSMILE`.
   - Objetivo: medir entonación (pitch), duración, ritmo, pausas, energía y claridad vocálica.
4. **Motor de evaluación (scoring)**
   - Inicial: reglas heurísticas (desviación de duración, pausas, errores de palabra).
   - Evolutivo: modelo propio con `PyTorch`/`SpeechBrain` (GOP o scoring supervisado).
5. **Feedback pedagógico para el usuario**
   - Herramienta: LLM para explicar errores en lenguaje simple.
   - Objetivo: devolver "qué corregir" + "cómo practicar" (sin vidas/puntuación desmotivadora).

### Mínimo viable recomendado con vuestro stack actual

- Usar ElevenLabs/Whisper para STT.
- Añadir `WhisperX` para timestamps por palabra.
- Añadir `Parselmouth` para pitch y ritmo.
- Implementar un endpoint `POST /pronunciation-feedback` que devuelva:
  - palabras omitidas o mal reconocidas,
  - velocidad estimada,
  - pausas excesivas,
  - consejo corto de práctica.

Con esto ya podéis tener evaluación útil sin montar un sistema fonético completo desde el día 1.


## Coste del preprocesado y análisis (además del STT)

Si mantenéis 100 audios/mes, estos componentes suelen tener más coste de infraestructura/tiempo que de licencia.

### Licencia de herramientas

- `ffmpeg`: **gratis** (open-source). Es robusto, pero puede sentirse "pesado" por cantidad de opciones y flags.
- `Whisper`/`faster-whisper`: **gratis** (open-source) si lo corréis en vuestra infraestructura.
- `MFA`: **gratis** (open-source).
- `Parselmouth`/`Praat`: **gratis** (open-source).

### Dónde sí aparece coste real

1. **CPU/GPU y almacenamiento**
   - Preprocesado (`ffmpeg`, VAD, recortes) consume CPU pero para 100 audios/mes suele ser bajo.
   - Alineación (`WhisperX`/`MFA`) puede aumentar tiempo de cómputo por audio.
   - Guardar audios + resultados (JSON/features) añade almacenamiento.
2. **Mantenimiento técnico**
   - Ajustes de pipeline, monitorización y resolución de errores.
3. **Servicios externos opcionales**
   - Si el feedback pedagógico lo hace un LLM por API (p. ej. ChatGPT API), aparece coste por tokens.

### Estimación orientativa mensual para 100 audios

> Orden de magnitud, no presupuesto cerrado.

- **Preprocesado con `ffmpeg` + VAD**: licencia USD 0; infraestructura típicamente baja (normalmente << USD 1–2/mes en uso pequeño).
- **Alineación (`WhisperX` o `MFA`)**: licencia USD 0; infraestructura variable según hardware (puede ser de céntimos a pocos USD/mes con este volumen).
- **Análisis acústico (`Parselmouth`/`librosa`)**: licencia USD 0; coste de cómputo bajo en este volumen.
- **LLM opcional (ChatGPT API)**: coste variable por tokens; para feedback corto de 100 audios/mes suele ser bajo, pero depende del modelo y longitud del prompt/respuesta.

### Recomendación de control de coste

- Guardar métricas de tiempo por etapa: `preprocess_ms`, `align_ms`, `analyze_ms`, `llm_tokens`.
- Empezar sin LLM o con respuestas muy cortas y plantillas.
- Activar LLM solo cuando la confianza del análisis sea baja o para errores recurrentes.
- Revisar al final de mes coste real vs. estimado y ajustar.

## Si añades evaluación de pronunciación en APIs de pago

- En algunos proveedores la evaluación de pronunciación se integra sobre STT y puede no tener coste separado, mientras que en otros sí puede aplicar coste adicional.
- Recomendación: presupuestar **hasta x2** del coste STT durante pruebas para cubrir:
  - evaluación extra por fonema/palabra,
  - reintentos,
  - TTS para feedback,
  - almacenamiento de audios.

## Orden de magnitud esperado para vuestro caso

Con 100 audios/mes, el coste de STT suele ser **muy bajo** (normalmente en el rango de **céntimos a pocos dólares al mes**, según duración real y proveedor).

## Recomendación práctica

1. Empezar con stack open-source simple: `faster-whisper`.
2. Medir 1 mes de uso real (duración media + reintentos).
3. Ajustar con reglas por idioma (ej. japonés entre semana, inglés fin de semana).
4. Escalar calidad por capas (`WhisperX` → `Parselmouth/librosa` → `MFA`).

## Ejemplo aplicado a una actividad de juego (pronunciación guiada)

Para aterrizar la arquitectura en una actividad real, aquí tienes un flujo para el juego **"Audio y pronunciación correcta"**.

### Objetivo de la actividad

- El usuario escucha una frase objetivo (idioma activo del día).
- El usuario graba su intento.
- El sistema devuelve feedback amable (sin vidas ni puntuación punitiva):
  - qué palabra/sílaba mejorar,
  - ritmo/pausas,
  - sugerencia corta de práctica.

### Flujo técnico por servicios

1. `game-content-service`
   - Entrega el ejercicio: `expected_text`, audio de referencia, idioma (`ja` o `en`) y nivel.
2. `speech-service` (STT actual)
   - Usa ElevenLabs STT o Whisper (Home Assistant) para obtener transcripción inicial.
3. `audio-preprocess-service`
   - `ffmpeg`/`sox` para normalizar audio (mono, 16kHz), recortar silencios y limpiar entrada.
4. `alignment-service`
   - `WhisperX` (rápido) o `MFA` (más preciso) para mapear audio ↔ palabras/fonemas.
5. `acoustic-analysis-service`
   - `Parselmouth`/`librosa` para pitch, duración, pausas y ritmo.
6. `feedback-service`
   - Reglas heurísticas + (opcional) ChatGPT API para explicación pedagógica corta.
7. `orchestrator-api`
   - Devuelve al frontend JSON con resultados listos para UI.

### JSON de salida recomendado para la actividad

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

### Encaje con tu política por idioma (semana/fines de semana)

- `policy-service` puede seleccionar automáticamente:
  - Lunes a viernes: actividades de pronunciación en japonés.
  - Fines de semana: actividades equivalentes en inglés.
- El flujo técnico no cambia; solo cambian `language`, contenido y reglas fonéticas.

### Coste incremental de esta actividad

- Reutiliza tu STT existente (ElevenLabs/Whisper).
- Añade coste de cómputo por preprocesado + alineación + análisis acústico.
- LLM (ChatGPT API) se puede dejar opcional para no elevar coste al inicio.
