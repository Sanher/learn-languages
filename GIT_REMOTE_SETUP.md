# Configuración de remoto (Git) en este proyecto

Guía rápida para conectar el repositorio local con GitHub/GitLab y poder hacer `pull/push`.

## 1) Ver estado actual

```bash
git remote -v
git branch --show-current
```

Si `git remote -v` no muestra nada, no hay remoto configurado.

## 2) Añadir remoto `origin`

```bash
git remote add origin <URL_DEL_REPO>
```

Ejemplos:

```bash
git remote add origin git@github.com:tu-org/learn-languages.git
# o
git remote add origin https://github.com/tu-org/learn-languages.git
```

## 3) Verificar configuración

```bash
git remote -v
```

## 4) Subir rama actual por primera vez

```bash
git push -u origin work
```

## 5) Bajar cambios

```bash
git fetch origin
git pull origin work
```

## 6) Si necesitas cambiar la URL del remoto

```bash
git remote set-url origin <NUEVA_URL>
git remote -v
```

## ¿Se puede hacer desde Codex web?

Sí. Si la sesión de Codex web tiene terminal y credenciales válidas, puedes ejecutar exactamente los mismos comandos anteriores.
