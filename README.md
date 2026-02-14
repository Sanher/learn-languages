# learn-languages

Implementación inicial de una actividad de juego de **pronunciación guiada** con arquitectura por servicios (a nivel de código de dominio).

## Qué incluye

- Política por idioma según día:
  - lunes a viernes `ja`
  - fin de semana `en`
- Pipeline de actividad de pronunciación:
  - entrada esperada y reconocida,
  - métricas de confianza, ritmo, pausas y estabilidad de pitch,
  - feedback por palabra,
  - siguiente paso sugerido.

## Archivos clave

- `language_games/policy.py`
- `language_games/pronunciation.py`
- `demo_pronunciation_activity.py`
- `tests/test_pronunciation.py`

## Ejecutar demo

```bash
python demo_pronunciation_activity.py
```

## Ejecutar tests

```bash
python -m unittest discover -s tests
```


## Documento de arquitectura

- `ESTRUCTURA_GENERAL.md`: visión general de servicios, flujo de análisis de audio y plan de implementación por fases.


## Operativa Git

- `GIT_REMOTE_SETUP.md`: pasos para configurar remoto (`origin`) y trabajar con `pull/push` también desde Codex web.
