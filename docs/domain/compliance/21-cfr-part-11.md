---
title: 21 CFR Part 11
status: skeleton
applies_to: clientes farma / dispositivos médicos / alimentos en mercado USA.
last_updated: 2026-05-04
---

# 21 CFR Part 11

> **Estado:** placeholder. El Architect debe completar este documento antes de cualquier feature en `apps/quality/` o `apps/traceability/` cuando un cliente activo requiera 21 CFR Part 11.

## Qué exige (resumen)

- Registros electrónicos auditables (audit trail inmutable, append-only).
- Firmas electrónicas con autenticación robusta y atribución no repudiable.
- Validación de sistemas (CSV — Computer System Validation).
- Control de acceso por rol con segregación de funciones.
- Backups y procedimientos de recuperación documentados.

## Implicaciones en nuestro código

1. **Audit log mandatorio** (`golden-principles.md` GP-009): toda escritura a entidades reguladas pasa por un audit log inmutable que registra quién, qué, cuándo, por qué.
2. **Firma electrónica** en transiciones de estado clave: liberar OF, cerrar NCR, aprobar receta. Mecanismo a definir (TOTP / certificado / biométrico).
3. **No hay hard delete** para entidades reguladas. Solo soft delete con motivo.
4. **Trazabilidad de cambios de configuración** del propio sistema (cambios al catálogo de razones de paro, planes de inspección, etc.).

## Open questions

- TODO: ¿qué método de firma electrónica adopta NSG por default?
- TODO: ¿quién valida el sistema (CSV) — externo o interno?
- TODO: período de retención de logs (mínimo 7 años para algunos sub-sectores).
