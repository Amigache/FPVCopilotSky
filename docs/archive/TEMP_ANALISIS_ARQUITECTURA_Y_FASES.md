# Plan Tecnico Temporal - Modo Standby Ejecutable

Fecha: 28-05-2026
Estado: Preparado para ejecucion bajo demanda
Uso: Este plan no se ejecuta ahora. Se activa cuando el usuario lo solicite.

## 1. Para que sirve este documento

Concentrar en un solo lugar:

- Diagnostico tecnico ya realizado.
- Roadmap por fases para ejecutar mejoras.
- Criterios de inicio, control y cierre por fase.

Este archivo esta pensado como runbook: cuando el usuario diga "empezamos", se ejecuta fase por fase.

## 2. Diagnostico consolidado

### Fortalezas actuales

- Producto funcional y amplio (telemetria, video, red, modem, VPN, UI).
- Arquitectura de providers bien orientada a hardware heterogeneo.
- Base de pruebas existente y pipelines de calidad ya instalados.

### Riesgos principales detectados

1. Cobertura efectiva baja para el tamano del backend.
2. Parte de la suite de tests valida estados demasiado permisivos.
3. Hotspots de complejidad en modulos backend y vistas frontend.
4. Operaciones privilegiadas acopladas a API/rutas.
5. Flujo de update/rollback con pasos potencialmente destructivos.
6. Observabilidad mejorable por manejo generico de excepciones.
7. Inconsistencias de documentacion frente al codigo real.
8. Oportunidades de optimizacion de estado y polling en frontend.

## 3. Metas tecnicas globales (resultado esperado)

Al terminar el plan:

- Mayor confiabilidad de CI y menor tasa de regresiones.
- Menor costo de cambio en modulos criticos.
- Operaciones de sistema mas seguras y auditables.
- Diagnostico de fallos mas rapido con logs/errores estandarizados.
- Documentacion alineada con el estado real del repositorio.

## 4. Reglas de ejecucion (cuando se active)

### 4.1 Modo de trabajo

- Ejecucion incremental por fases.
- No mezclar mas de 1 objetivo critico por PR si hay riesgo alto.
- Validacion tecnica al cerrar cada fase.

### 4.2 Gating por fase

No se inicia la siguiente fase si no se cumplen los criterios de salida de la fase actual.

### 4.3 Criterio de rollback

Si una fase degrada estabilidad o rompe CI de forma no trivial, se pausa y se aplica rollback tecnico del bloque afectado.

## 5. Roadmap por fases (ejecutable)

## Fase 0 - Baseline y alineacion

Duracion estimada: 1 semana
Objetivo: fijar linea base medible y eliminar ambiguedad tecnica.

Tareas:

- Consolidar inventario real de modulos hotspot (back/front/tests/docs).
- Registrar metricas base: cobertura, duracion de tests, fallos por dominio.
- Alinear documentacion critica con el estado actual del repo.

Entregables:

- Baseline tecnico versionado.
- Checklist de consistencia docs-codigo.

Criterio de salida:

- Baseline aprobado y listo para comparativas.

## Fase 1 - Calidad y CI confiable

Duracion estimada: 2 semanas
Objetivo: subir confianza de test sin frenar entregas.

Tareas:

- Endurecer tests permisivos en endpoints de alto riesgo.
- Aislar completamente comandos privilegiados en pruebas.
- Establecer aumento gradual de gate de cobertura (por etapas).
- Garantizar suite no interactiva para CI.

Entregables:

- CI determinista.
- Politica de cobertura incremental aplicada.

Criterio de salida:

- Pipeline verde sin prompts interactivos.

## Fase 2 - Refactor backend de hotspots

Duracion estimada: 3 a 4 semanas
Objetivo: bajar complejidad y acoplamiento accidental.

Tareas:

- Modularizar arranque/lifecycle en backend.
- Separar rutas modem por subdominios funcionales.
- Dividir responsabilidades del servicio WebRTC.
- Introducir capa de casos de uso para desacoplar rutas.

Entregables:

- Archivos hotspot reducidos y mas cohesionados.
- Menor impacto lateral por cambio.

Criterio de salida:

- Refactor validado por tests y sin regresiones criticas.

## Fase 3 - Operacion segura y privilegios

Duracion estimada: 2 a 3 semanas
Objetivo: endurecer operaciones root/update.

Tareas:

- Centralizar ejecucion privilegiada en un executor controlado.
- Definir allowlist y formato estandar de resultados de comandos.
- Introducir update seguro con precheck + backup + rollback.
- Revisar flujo actual para evitar opciones destructivas por defecto.

Entregables:

- Capa de ejecucion operativa segura y auditable.
- Flujo de update/rollback robusto.

Criterio de salida:

- Operaciones sensibles trazables y reproducibles.

## Fase 4 - Observabilidad y errores tipados

Duracion estimada: 2 semanas
Objetivo: acelerar diagnostico y reducir errores silenciosos.

Tareas:

- Sustituir prints por logging estructurado en servicios core.
- Migrar excepciones genericas a errores tipados en rutas/servicios criticos.
- Estandarizar payload de error API.
- Agregar metricas minimas operativas por dominio.

Entregables:

- Politica de errores uniforme.
- Observabilidad operativa minima.

Criterio de salida:

- Diagnostico consistente por logs y codigos de error.

## Fase 5 - Optimizacion frontend tecnica

Duracion estimada: 2 a 3 semanas
Objetivo: simplificar estado y reducir trabajo innecesario.

Tareas:

- Definir estrategia WS-first por vista con fallback acotado.
- Reducir polling continuo donde ya exista canal WS estable.
- Extraer logica de estado en hooks reutilizables.
- Fraccionar vistas grandes en bloques testeables.

Entregables:

- Vistas mas mantenibles y predecibles.
- Menor deuda de estado en UI.

Criterio de salida:

- Menor complejidad en vistas y sin degradacion UX.

## Fase 6 - Consolidacion y release hardening

Duracion estimada: 1 a 2 semanas
Objetivo: cerrar con release tecnica estable.

Tareas:

- Regresion integral backend/frontend.
- Validacion de scripts operativos en entorno limpio.
- Reconciliacion final de documentacion.
- Reporte comparativo contra baseline.

Entregables:

- Candidato de release con evidencia tecnica.
- Informe final de mejoras.

Criterio de salida:

- Rama lista para release con metricas verificadas.

## 6. Priorizacion de ejecucion

Orden recomendado:

1. Fase 0
2. Fase 1
3. Fase 2
4. Fase 3
5. Fase 4
6. Fase 5
7. Fase 6

Nota:

- Fase 2 y Fase 3 pueden solaparse parcialmente si hay capacidad.

## 7. Riesgos y mitigaciones operativas

- Riesgo: refactor amplio bloquee flujo de features.
  Mitigacion: lotes pequenos y criterios de merge estrictos.

- Riesgo: subir coverage demasiado rapido bloquee equipo.
  Mitigacion: incremento gradual por dominio critico.

- Riesgo: cambios de privilegios rompan instalaciones reales.
  Mitigacion: staging + checklist de rollback operativo.

## 8. Modo de activacion (cuando el usuario lo pida)

Trigger sugerido:

- "Empezamos Fase X"
- "Ejecuta Fase 0"
- "Arranca el plan de endurecimiento"

Respuesta esperada del asistente al activarse:

1. Confirmar fase activa.
2. Ejecutar tareas de esa fase en orden.
3. Reportar avance con evidencia.
4. Cerrar fase con checklist de salida.

## 9. Quick wins (si se quiere iniciar con bajo riesgo)

- Corregir inconsistencias docs-codigo.
- Endurecer tests API mas permisivos.
- Normalizar logging en servicios con prints.
- Dividir primer hotspot backend por subdominios.

## 10. Nota de temporalidad

Este archivo es temporal. Si el plan se valida en ejecucion real, migrar contenido final a documentacion permanente del proyecto.
