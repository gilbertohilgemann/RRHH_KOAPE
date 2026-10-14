# KOAPE RRHH & PAYROLL — Especificación técnica para Claude
**Versión 1.0 | 13/10/2026 | Paraguay**  
**Roles:** GPT = arquitecto; Claude = constructor/implementador.

## 1. Orden principal para Claude

Antes de escribir código:
1. Inspeccionar repositorio, lenguaje/framework, versiones, ORM, base de datos, autenticación, multiempresa, RBAC, navegación, UI, auditoría, archivos, pruebas, despliegue y migraciones.
2. Localizar módulos de ejemplo y definiciones XML. Si existen `PayRoll.modulo.xml`, archivos de ventanas/formularios (`*.windows.xml` o nombre real del proyecto) y `record.xml`, analizar su sintaxis y seguirla exactamente. No inventar otro formato.
3. Confirmar convenciones de tablas y campos, especialmente que las PK existentes usan `internalId`, estilo PascalCase, nombres de FK, índices y campos de auditoría.
4. Reutilizar `Company`, sucursales, usuarios, roles, permisos, archivos y bitácora existentes. No duplicar entidades comunes.
5. Presentar diagnóstico y plan por fases antes de cambios de alto impacto. No ejecutar `DROP`, truncados, migraciones destructivas ni borrados de evidencia sin autorización.
6. Implementar sistema funcional: backend, persistencia, validaciones, permisos, transacciones, interfaz, importador real, cálculo, reportes, pruebas y documentación. No dejar botones de maqueta.

### Convenciones Koape
- PK `internalId`, adaptando el tipo y generación a la base existente.
- PascalCase para tablas/campos si coincide con el proyecto (`Employee`, `PayrollRun`, `CreatedAt`).
- Aislamiento multiempresa por `CompanyId` o equivalente real; verificar pertenencia en backend, nunca confiar en el ID enviado desde frontend.
- Mantener auditoría común. Si existe `EventLog`, reutilizarlo y respetar su configuración/política de sincronización.
- Si Koape utiliza XML para módulos, registros, formularios, reportes y rutinas, producir los archivos correspondientes con la estructura ya usada.
- No alterar módulos no relacionados.

## 2. Objetivo funcional
Módulo integral para legajos, contratos, historial salarial, horarios, marcaciones, importación de CSV de relojes, asistencia, incidencias, horas extra, permisos, vacaciones, licencias, comisiones, bonos, descuentos, anticipos, préstamos, nómina, aportes del trabajador, cargas patronales, costo patronal, aguinaldo, recibos, liquidación final, reportes y preparación de información para MTESS/IPS.

El sistema debe soportar salario base por hora, día/jornal, semana, quincena, mes, comisión, pieza/producción y esquemas mixtos; la frecuencia de pago se guarda por separado de la base salarial.

## 3. Arquitectura
Capas: (1) maestros y legajos; (2) asistencia/importaciones; (3) novedades y autorizaciones; (4) motor legal versionado; (5) cálculo de nómina; (6) pagos/recibos; (7) cumplimiento/exportaciones; (8) seguridad/auditoría.

Estados sugeridos:
- Importación: `Uploaded`, `Previewed`, `Validated`, `PartiallyRejected`, `Committed`, `Cancelled`.
- Novedad/licencia: `Draft`, `Submitted`, `Approved`, `Rejected`, `Applied`, `Cancelled`.
- Nómina: `Draft`, `Calculated`, `UnderReview`, `Approved`, `Closed`, `Paid`, `Reopened`, `Rectified`, `Cancelled`.
- Documento: `Draft`, `Issued`, `Voided`, `Replaced`.

Los estados y transiciones se validan en backend. Nóminas cerradas no se modifican en silencio: las correcciones crean una rectificación enlazada.

## 4. Modelo de datos

El modelo es lógico. Antes de crear una tabla, Claude debe verificar si ya existe una entidad equivalente. Todas las entidades transaccionales llevan `CompanyId` salvo catálogos realmente globales. Importes: `DECIMAL`, nunca `FLOAT`; fechas/horas nativas; restricciones, FKs e índices reales. Evitar borrado físico de registros laborales/salariales.

### 4.1 Maestros y legajo
**`Employee`**: `internalId` PK, `CompanyId`, `EmployeeCode`, `DocumentType`, `DocumentNumber`, `FirstName`, `MiddleName`, `LastName`, `SecondLastName`, `BirthDate`, `PersonalEmail`, `WorkEmail`, `Phone`, `Address`, `HireDate`, `TerminationDate`, `EmploymentStatus`, `BranchId`, `DepartmentId`, `PositionId`, `CostCenterId`, `SupervisorEmployeeId`, `Notes`, `CreatedAt`, `CreatedBy`, `UpdatedAt`, `UpdatedBy`, `IsActive`. `UNIQUE(CompanyId, EmployeeCode)`.
**`Department`**: `internalId`, `CompanyId`, `Code`, `Name`, `ParentDepartmentId`, `ManagerEmployeeId`, `IsActive`. `UNIQUE(CompanyId, Code)`.
**`Position`**: `internalId`, `CompanyId`, `Code`, `Name`, `Description`, `IsActive`.
**`CostCenter`**: `internalId`, `CompanyId`, `Code`, `Name`, `ParentCostCenterId`, `IsActive`.
**`EmployeeAssignmentHistory`**: `internalId`, `CompanyId`, `EmployeeId`, `BranchId`, `DepartmentId`, `PositionId`, `CostCenterId`, `SupervisorEmployeeId`, `ValidFrom`, `ValidTo`, `Reason`, `ApprovedBy`.
**`EmployeeContract`**: `internalId`, `CompanyId`, `EmployeeId`, `ContractNumber`, `ContractType`, `StartDate`, `EndDate`, `WorkRegimeId`, `WorkScheduleId`, `SalarySchemeId`, `PaymentFrequency`, `SalaryAmount`, `CurrencyCode`, `SocialSecurityRegimeId`, `Status`, `TerminationReason`, `SignedDocumentId`, `CreatedAt`, `CreatedBy`.
**`EmployeeSalaryHistory`**: `internalId`, `CompanyId`, `EmployeeId`, `EmployeeContractId`, `ValidFrom`, `ValidTo`, `SalarySchemeId`, `BaseSalary`, `HourlyRate`, `DailyRate`, `CurrencyCode`, `PaymentFrequency`, `Reason`, `ApprovedBy`, `ApprovedAt`, `SourceDocumentId`, `CreatedAt`, `CreatedBy`. Impedir vigencias solapadas no autorizadas.
**`EmployeeDocument`**: `internalId`, `CompanyId`, `EmployeeId`, `DocumentTypeId`, `FileId/StorageKey`, `OriginalFileName`, `MimeType`, `SizeBytes`, `Checksum`, `IssueDate`, `ExpiryDate`, `IsConfidential`, `UploadedAt`, `UploadedBy`, `Status`.
**`EmployeeBankAccount`** (acceso restringido): `internalId`, `CompanyId`, `EmployeeId`, `BankCode`, `AccountType`, `AccountNumberEncrypted` o referencia a bóveda, `AccountHolder`, `IsPrimary`, `ValidFrom`, `ValidTo`. Nunca exponer cuenta completa en listados/logs.

### 4.2 Jornada y asistencia
**`WorkRegime`**: `internalId`, `Code`, `Name`, `DayType` (Day/Night/Mixed/Other), `LegalRuleSetId`, `MaxDailyMinutes`, `MaxWeeklyMinutes`, `IsActive`.
**`WorkSchedule`**: `internalId`, `CompanyId`, `Code`, `Name`, `WorkRegimeId`, `GraceMinutes`, `BreakPolicy`, `CrossesMidnight`, `EffectiveFrom`, `EffectiveTo`, `IsActive`.
**`WorkScheduleDay`**: `internalId`, `WorkScheduleId`, `DayOfWeek`, `StartTime`, `EndTime`, `BreakMinutes`, `IsWorkday`, `Sequence`; permitir múltiples tramos por día.
**`ShiftAssignment`**: `internalId`, `CompanyId`, `EmployeeId`, `WorkScheduleId`, `ValidFrom`, `ValidTo`, `AssignedBy`, `ApprovedBy`.
**`HolidayCalendar`**: `internalId`, `CompanyId` nullable, `Code`, `Name`, `Year`, `IsActive`.
**`HolidayCalendarDay`**: `internalId`, `HolidayCalendarId`, `HolidayDate`, `Name`, `HolidayType`, `LegalTreatmentRuleId`.
**`TimeClockDevice`**: `internalId`, `CompanyId`, `Code`, `Name`, `Manufacturer`, `Model`, `DeviceSerial`, `Location`, `TimeZoneId`, `ImportProfileId`, `IsActive`.
**`TimeClockEmployeeMap`**: `internalId`, `CompanyId`, `TimeClockDeviceId`, `DeviceEmployeeCode`, `EmployeeId`, `ValidFrom`, `ValidTo`, `Notes`. El código del reloj no se asume igual al código de Koape.
**`AttendanceImportProfile`**: `internalId`, `CompanyId`, `Code`, `Name`, `Delimiter`, `Encoding`, `HasHeader`, `DateFormat`, `TimeFormat`, `QuoteChar`, `EmployeeCodeColumn`, `TimestampColumn`, `DateColumn`, `TimeColumn`, `PunchTypeColumn`, `DeviceIdColumn`, `EventIdColumn`, `ColumnMappingJson`, `TransformRulesJson`, `DefaultTimeZoneId`, `DuplicateStrategy`, `Version`, `IsActive`. `TransformRulesJson` solo admite reglas declarativas seguras; no código ejecutable.
**`AttendanceImportBatch`**: `internalId`, `CompanyId`, `TimeClockDeviceId`, `AttendanceImportProfileId`, `OriginalFileName`, `StorageKey`, `FileChecksum`, `FileSizeBytes`, `UploadedAt`, `UploadedBy`, `PeriodFrom`, `PeriodTo`, `Status`, `TotalRows`, `AcceptedRows`, `RejectedRows`, `DuplicateRows`, `WarningsCount`, `CommittedAt`, `CommittedBy`, `ErrorSummary`.
**`AttendanceImportRow`**: `internalId`, `CompanyId`, `AttendanceImportBatchId`, `RowNumber`, `RawRowJson/RawText`, `DeviceEmployeeCode`, `EmployeeId`, `PunchDateTime`, `PunchType`, `DeviceEventId`, `NormalizedHash`, `ValidationStatus`, `ValidationMessages`, `AttendancePunchId`. `UNIQUE(AttendanceImportBatchId, RowNumber)`.
**`AttendancePunch`**: `internalId`, `CompanyId`, `EmployeeId`, `TimeClockDeviceId`, `PunchDateTime`, `PunchType` (IN/OUT/BREAK_START/BREAK_END/UNKNOWN), `SourceType` (Import/Manual/API), `SourceBatchId`, `SourceRowId`, `ExternalEventId`, `DeduplicationHash`, `IsManualCorrection`, `CorrectionReason`, `CorrectedFromPunchId`, `CreatedAt`, `CreatedBy`, `ApprovedBy`.
**`AttendanceDay`**: `internalId`, `CompanyId`, `EmployeeId`, `WorkDate`, `WorkScheduleId`, `FirstIn`, `LastOut`, `WorkedMinutes`, `BreakMinutes`, `LateMinutes`, `EarlyLeaveMinutes`, `OrdinaryMinutes`, `OvertimeCandidateMinutes`, `NightMinutes`, `HolidayMinutes`, `MissingPunchCount`, `AttendanceStatus`, `CalculationVersion`, `CalculatedAt`, `ReviewedBy`, `ReviewedAt`, `Notes`.
**`AttendanceIncident`**: `internalId`, `CompanyId`, `EmployeeId`, `WorkDate`, `IncidentType`, `StartAt`, `EndAt`, `Minutes`, `Description`, `SourcePunchId`, `Status`, `RequestedBy`, `ApprovedBy`, `ApprovedAt`, `Resolution`.
**`AttendanceManualAdjustment`**: `internalId`, `CompanyId`, `EmployeeId`, `WorkDate`, `OriginalPunchId`, `AdjustedPunchDateTime`, `PunchType`, `Reason`, `RequestedBy`, `ApprovedBy`, `ApprovedAt`, `Status`.
**`OvertimeAuthorization`**: `internalId`, `CompanyId`, `EmployeeId`, `WorkDate`, `StartAt`, `EndAt`, `MinutesRequested`, `MinutesApproved`, `Reason`, `Status`, `RequestedBy`, `ApprovedBy`, `ApprovedAt`, `PayrollRunId`.

### 4.3 Licencias y vacaciones
**`LeaveType`**: `internalId`, `CompanyId` nullable/global, `Code`, `Name`, `LeaveCategory`, `IsPaid`, `ConsumesVacationBalance`, `RequiresDocument`, `RequiresApproval`, `PayrollTreatmentRuleId`, `LegalRuleSetId`, `MaxDays`, `IsActive`.
**`LeaveRequest`**: `internalId`, `CompanyId`, `EmployeeId`, `LeaveTypeId`, `StartDate`, `EndDate`, `StartTime`, `EndTime`, `RequestedDays`, `RequestedMinutes`, `Reason`, `SupportingDocumentId`, `Status`, `RequestedAt`, `ApprovedBy`, `ApprovedAt`, `ActualStartDate`, `ActualEndDate`, `CancellationReason`.
**`VacationMovement`**: `internalId`, `CompanyId`, `EmployeeId`, `MovementDate`, `MovementType` (Accrual/Taken/Adjustment/Expired/Correction), `Days`, `LeaveRequestId`, `PayrollRunId`, `Reason`, `ApprovedBy`.
**`EmployeeAbsence`**: `internalId`, `CompanyId`, `EmployeeId`, `AbsenceDate`, `AbsenceType`, `Minutes`, `IsJustified`, `LeaveRequestId`, `PayrollTreatmentRuleId`, `Status`.
**`EmployeeMedicalCertificate`**: `internalId`, `CompanyId`, `EmployeeId`, `StartDate`, `EndDate`, `Issuer`, `CertificateNumber`, `FileId`, `Status`, `ReceivedAt`, `ReceivedBy`. Datos médicos con permisos estrictos y sin diagnósticos en reportes generales.

### 4.4 Conceptos salariales y novedades
**`SalaryScheme`**: `internalId`, `CompanyId` nullable/global, `Code`, `Name`, `CalculationBasis` (Hourly/Daily/Weekly/Biweekly/Monthly/Commission/Piecework/Mixed), `PaymentFrequency`, `IsActive`, `Description`.
**`PayrollConcept`**: `internalId`, `CompanyId` nullable/global, `Code`, `Name`, `ConceptType` (Earning/Deduction/EmployeeContribution/EmployerContribution/Informational), `CalculationType` (Fixed/QuantityRate/Percentage/Formula/ImportedAmount/ManualAmount), `DefaultBase`, `DefaultRate`, `AffectsNetPay`, `AffectsAguinaldoBase`, `AffectsVacationBase`, `AffectsSocialSecurityBase`, `AffectsEmployerCost`, `IsTaxable`, `IsRecurring`, `RequiresApproval`, `RequiresEvidence`, `DisplayOrder`, `IsActive`.
**`PayrollConceptRule`**: `internalId`, `CompanyId` nullable, `PayrollConceptId`, `LegalRuleSetId`, `ValidFrom`, `ValidTo`, `ConditionJson`, `CalculationExpression`, `RoundingMode`, `Priority`, `IsActive`, `ApprovedBy`. Motor de reglas seguro; nunca `eval` ni SQL arbitrario.
**`RecurringEmployeeConcept`**: `internalId`, `CompanyId`, `EmployeeId`, `PayrollConceptId`, `Amount`, `Rate`, `Quantity`, `ValidFrom`, `ValidTo`, `Frequency`, `CostCenterId`, `ApprovedBy`, `SourceDocumentId`, `IsActive`.
**`PayrollIncident`**: `internalId`, `CompanyId`, `EmployeeId`, `PayrollConceptId`, `PeriodStart`, `PeriodEnd`, `Quantity`, `Rate`, `Amount`, `CurrencyCode`, `Description`, `SourceType`, `SourceRecordId`, `Status`, `RequestedBy`, `ApprovedBy`, `ApprovedAt`, `AppliedPayrollRunId`.
**`CommissionRecord`**: `internalId`, `CompanyId`, `EmployeeId`, `PeriodStart`, `PeriodEnd`, `SalesBase`, `Rate`, `Amount`, `Reference`, `ApprovedBy`, `Status`, `PayrollIncidentId`.
**`EmployeeBonus`**: `internalId`, `CompanyId`, `EmployeeId`, `BonusType`, `PeriodStart`, `PeriodEnd`, `Amount`, `Reason`, `ApprovalStatus`, `ApprovedBy`, `PayrollIncidentId`.
**`EmployeeDeduction`**: `internalId`, `CompanyId`, `EmployeeId`, `DeductionType`, `Amount`, `InstallmentAmount`, `Balance`, `StartDate`, `EndDate`, `AuthorizedByEmployee`, `AuthorizationDocumentId`, `Priority`, `Status`, `PayrollConceptId`.
**`EmployeeAdvance`**: `internalId`, `CompanyId`, `EmployeeId`, `AdvanceDate`, `RequestedAmount`, `ApprovedAmount`, `PaidAmount`, `CurrencyCode`, `Reason`, `Status`, `PaymentMethod`, `PaymentReference`, `PayrollConceptId`, `ApprovedBy`, `PaidAt`, `RecoveryPolicy`, `Balance`.
**`EmployeeLoan`**: `internalId`, `CompanyId`, `EmployeeId`, `LoanDate`, `PrincipalAmount`, `CurrencyCode`, `InstallmentCount`, `InstallmentAmount`, `OutstandingBalance`, `InterestRate`, `StartPayrollPeriodId`, `Status`, `AuthorizationDocumentId`, `ApprovedBy`.
**`EmployeeLoanInstallment`**: `internalId`, `CompanyId`, `EmployeeLoanId`, `PayrollPeriodId`, `DueAmount`, `AppliedAmount`, `Balance`, `Status`, `PayrollRunId`.

### 4.5 Reglas legales versionadas
**`LegalRuleSet`**: `internalId`, `Code`, `Name`, `CountryCode` (PY), `RegimeCode`, `ValidFrom`, `ValidTo`, `SourceName`, `SourceNumber`, `SourceUrl`, `PublishedAt`, `VerifiedBy`, `VerifiedAt`, `Status` (Draft/Reviewed/Approved/Retired), `Notes`.
**`LegalParameter`**: `internalId`, `LegalRuleSetId`, `ParameterCode`, `ParameterName`, `NumericValue`, `TextValue`, `JsonValue`, `Unit`, `ValidFrom`, `ValidTo`, `SourceReference`.
**`SocialSecurityRegime`**: `internalId`, `Code`, `Name`, `EmployeeRate`, `EmployerRate`, `ContributionBaseRuleId`, `ValidFrom`, `ValidTo`, `SourceReference`, `IsActive`.
Nunca codificar tasas, salario mínimo, recargos, bases o excepciones como constantes permanentes. Cada versión tiene fuente, vigencia, estado de revisión y pruebas.

### 4.6 Nómina, recibos y costo patronal
**`PayrollPeriod`**: `internalId`, `CompanyId`, `Code`, `PeriodType` (Weekly/Biweekly/Monthly/Special), `StartDate`, `EndDate`, `PaymentDate`, `Status`, `CreatedBy`, `ClosedAt`, `ClosedBy`.
**`PayrollRun`**: `internalId`, `CompanyId`, `PayrollPeriodId`, `RunNumber`, `RunType` (Regular/Aguinaldo/Vacation/FinalSettlement/Adjustment), `CalculationVersion`, `LegalRuleSetId`, `Status`, `EmployeeCount`, `GrossTotal`, `EmployeeDeductionsTotal`, `EmployeeContributionsTotal`, `NetTotal`, `EmployerContributionsTotal`, `OtherEmployerCostTotal`, `TotalEmployerCost`, `CalculatedAt`, `CalculatedBy`, `ReviewedBy`, `ReviewedAt`, `ApprovedBy`, `ApprovedAt`, `ClosedAt`, `ClosedBy`, `ParentPayrollRunId`, `RectificationReason`. `UNIQUE(CompanyId, PayrollPeriodId, RunNumber)`.
**`PayrollEmployee`**: `internalId`, `CompanyId`, `PayrollRunId`, `EmployeeId`, `EmployeeContractId`, `WorkDays`, `PaidDays`, `UnpaidDays`, `OrdinaryMinutes`, `OvertimeMinutes`, `GrossPay`, `EmployeeDeductions`, `EmployeeContributions`, `NetPay`, `EmployerContributions`, `EmployerOtherCosts`, `TotalEmployerCost`, `AguinaldoAccruedAmount`, `VacationAccruedAmount`, `CalculationStatus`, `CalculationWarnings`, `PayslipDocumentId`, `PaymentStatus`, `PaidAt`. `UNIQUE(PayrollRunId, EmployeeId)`.
**`PayrollLine`**: `internalId`, `CompanyId`, `PayrollEmployeeId`, `PayrollConceptId`, `ConceptCodeSnapshot`, `ConceptNameSnapshot`, `ConceptTypeSnapshot`, `Quantity`, `Rate`, `BaseAmount`, `CalculatedAmount`, `SignedAmount`, `CurrencyCode`, `RuleVersionId`, `CalculationExplanation`, `SourceType`, `SourceRecordId`, `Sequence`, `IsManualOverride`, `OverrideReason`, `ApprovedBy`. Guardar snapshot para preservar recibos históricos.
**`PayrollPayment`**: `internalId`, `CompanyId`, `PayrollRunId`, `PayrollEmployeeId`, `PaymentDate`, `Amount`, `CurrencyCode`, `PaymentMethod`, `Reference`, `BankAccountId`, `Status`, `PaidBy`, `ConfirmedAt`, `ReceiptDocumentId`.
**`PayslipDocument`**: `internalId`, `CompanyId`, `PayrollRunId`, `PayrollEmployeeId`, `DocumentNumber`, `DocumentType` (Salary/Advance/Vacation/Aguinaldo/FinalSettlement/Adjustment), `IssueDate`, `PeriodStart`, `PeriodEnd`, `GrossAmount`, `DeductionsAmount`, `NetAmount`, `EmployerCostAmount` (interno), `FileId`, `Status`, `IssuedBy`, `IssuedAt`, `VoidedReason`.
**`AguinaldoAccrual`**: `internalId`, `CompanyId`, `EmployeeId`, `CalendarYear`, `EligibleRemunerationTotal`, `AccruedAmount`, `PaidAmount`, `Balance`, `LegalRuleSetId`, `LastCalculatedAt`, `Status`. Detalle computable debe reconstruirse desde líneas de nómina.
**`FinalSettlement`**: `internalId`, `CompanyId`, `EmployeeId`, `EmployeeContractId`, `TerminationDate`, `TerminationReason`, `SettlementDate`, `LegalRuleSetId`, `SalaryPending`, `VacationPay`, `AguinaldoProportional`, `NoticePay`, `SeverancePay`, `OtherEarnings`, `AuthorizedDeductions`, `GrossSettlement`, `NetSettlement`, `CalculationExplanation`, `Status`, `ApprovedBy`, `ApprovedAt`, `PayrollRunId`, `DocumentId`. Los conceptos aplicables dependen de causal, antigüedad y régimen.
**`EmployerCostAllocation`**: `internalId`, `CompanyId`, `EmployeeId`, `PayrollPeriodId`, `PayrollRunId`, `CostCenterId`, `GrossRemuneration`, `EmployerSocialContribution`, `EmployerBenefits`, `EmployerInsurance`, `OtherEmployerCost`, `TotalEmployerCost`, `CurrencyCode`.

Fórmula conceptual del costo patronal:
`TotalEmployerCost = GrossRemuneration + EmployerContributions + EmployerBenefits + EmployerInsurance + OtherEmployerCost`.
Las provisiones estimadas de aguinaldo/vacaciones se deben mostrar separadas del costo devengado/pagado y no sumarse dos veces. El aporte patronal no se descuenta del neto del trabajador.

### 4.7 Cumplimiento y documentos
**`ComplianceSubmission`**: `internalId`, `CompanyId`, `Authority` (MTESS/IPS/Other), `SubmissionType`, `PeriodStart`, `PeriodEnd`, `ReferenceNumber`, `Status`, `PreparedAt`, `PreparedBy`, `SubmittedAt`, `SubmittedBy`, `ResponseFileId`, `ErrorSummary`, `ExternalReceiptNumber`.
**`ComplianceSubmissionLine`**: `internalId`, `ComplianceSubmissionId`, `EmployeeId`, `PayloadJson`, `ValidationStatus`, `ValidationErrors`.
**`DocumentSequence`**: `internalId`, `CompanyId`, `DocumentType`, `Prefix`, `NextNumber`, `Year`, `IsActive`.
**`HRApproval`**: `internalId`, `CompanyId`, `EntityType`, `EntityId`, `Action`, `RequestedBy`, `AssignedApproverId`, `Status`, `DecisionAt`, `Comments`, `PreviousState`, `NewState`.
Si ya existe motor de aprobación o almacenamiento de documentos, reutilizarlo. La auditoría preferentemente se integra con la bitácora común Koape.

## 5. Relaciones principales
- `Employee` 1:N `EmployeeContract`, `EmployeeSalaryHistory`, `EmployeeAssignmentHistory`, `AttendancePunch`, `AttendanceDay`, `LeaveRequest`, `PayrollIncident`, `EmployeeAdvance`, `EmployeeLoan`.
- `EmployeeContract` 1:N `EmployeeSalaryHistory`.
- `Department`, `Position`, `CostCenter`, `Branch` 1:N `Employee`.
- `TimeClockDevice` 1:N `TimeClockEmployeeMap`; `Employee` 1:N `TimeClockEmployeeMap`.
- `AttendanceImportProfile` 1:N `AttendanceImportBatch`; batch 1:N `AttendanceImportRow`; row 0..1:N `AttendancePunch`.
- `WorkSchedule` 1:N `WorkScheduleDay`; asignación de horario por `ShiftAssignment`.
- `PayrollPeriod` 1:N `PayrollRun`; `PayrollRun` 1:N `PayrollEmployee`; `PayrollEmployee` 1:N `PayrollLine` y `PayrollPayment`.
- `PayrollConcept` 1:N `PayrollLine`, `PayrollConceptRule`, `RecurringEmployeeConcept`, `PayrollIncident`.
- `LegalRuleSet` 1:N `LegalParameter`, reglas de concepto y corridas.
- `EmployeeLoan` 1:N `EmployeeLoanInstallment`.
- `PayrollRun` 1:N `EmployerCostAllocation`.
Declarar FKs e índices reales. Toda relación debe validar empresa y vigencia.

## 6. Importación de marcaciones CSV: requisitos obligatorios
1. Subir CSV desde UI, seleccionar dispositivo/perfil/rango de fechas; soportar encabezado opcional.
2. Configurar delimitador coma, punto y coma o tabulación; UTF-8 y opción Latin-1/Windows-1252 si se requiere.
3. Configurar timestamp completo o columnas fecha/hora; formato explícito para evitar ambigüedad.
4. Mostrar vista previa y permitir mapear columnas; guardar perfil reutilizable.
5. Cargar primero a `AttendanceImportBatch` y `AttendanceImportRow` (staging), nunca directo a marcas finales.
6. Validar códigos del reloj mediante `TimeClockEmployeeMap`, empresa, estado del empleado en fecha, fechas/horas, zona horaria, tipo de marca, estructura y tamaño.
7. Filas desconocidas/invalidas se rechazan con motivo visible; nunca adivinar el empleado.
8. Detectar duplicados dentro del archivo y contra lotes anteriores usando ID externo o hash normalizado. Reimportar el mismo archivo debe ser idempotente.
9. Aceptar archivos parcialmente válidos y descargar CSV/XLSX de errores con número de fila, dato problemático y motivo.
10. Confirmación transaccional, checksum, usuario, dispositivo, perfil, fechas, contadores y auditoría.
11. Soportar marcas fuera de orden, varias marcas diarias y turnos que cruzan medianoche. No inventar entradas/salidas faltantes: crear incidencias.
12. No modificar marcas originales para corregirlas; usar ajuste nuevo enlazado, motivo y aprobación.
13. Revertir solo si no afecta nómina cerrada; si afecta período cerrado, crear corrección auditada.
14. Límites configurables de tamaño/filas; validar contenido real; no ejecutar macros; proteger CSV injection en exportaciones (`=`, `+`, `-`, `@`).
15. Recalcular asistencia de días afectados solo en períodos abiertos, sin duplicar novedades.


## 6 bis. Marcador propio de Koape: tres modalidades de registro

El sistema debe incluir un **marcador de entrada/salida propio**, además de admitir importaciones CSV de relojes externos. Debe permitir habilitar por empresa una o varias modalidades.

### Modalidad A — QR temporal desde el celular del empleado
1. El empleado inicia sesión en Koape desde su celular y entra a **Mi asistencia / Marcar entrada o salida**.
2. El empleado solicita un QR. El backend genera un token aleatorio, de uso único y vigencia breve (por ejemplo, 60 segundos, configurable).
3. El QR contiene únicamente un token opaco firmado o aleatorio, no el nombre, cédula, contraseña ni datos personales del empleado.
4. El empleado presenta el QR ante un lector disponible. El lector puede ser una terminal de Koape con cámara/lector QR o una página web autorizada que utilice la cámara del dispositivo lector.
5. El lector envía el token al backend por HTTPS. El backend valida vigencia, uso único, empresa, sesión que lo solicitó, estado del empleado y terminal autorizada.
6. Solo después de validar se registra la marca. Registrar fecha/hora del servidor, empleado, empresa, terminal, método `QR`, resultado y referencia de auditoría.
7. El token queda consumido al primer intento aceptado. Rechazar QR vencido, reutilizado, cancelado, de otra empresa o solicitado por usuario no habilitado.
8. El backend decide si corresponde entrada o salida según la secuencia y el horario, o muestra una selección explícita en el lector si así se configura. No aceptar dos entradas/salidas incoherentes sin generar incidencia.
9. El empleado debe ver confirmación clara de éxito o rechazo. La confirmación no puede depender solo de la pantalla del celular: el registro válido es el confirmado por el servidor.
10. No permitir que un QR estático del legajo sustituya al token temporal. Un QR permanente es copiable y no demuestra que el empleado está presente.

### Modalidad B — Código fijo del empleado
1. Cada empleado habilitado tiene un `AttendanceCode` único dentro de la empresa, generado por Koape y configurable en formato/longitud.
2. El código puede introducirse en una terminal, teclearse o leerse desde un código de barras/QR fijo si la empresa usa ese soporte. Esta modalidad identifica el código presentado, pero **no prueba por sí sola la identidad de quien lo presenta**.
3. La terminal debe estar autenticada/registrada, asociada a una empresa y habilitada para marcar. No aceptar códigos de empleados de otra empresa.
4. El código fijo no debe ser la contraseña de acceso a Koape ni permitir iniciar sesión. No incluir cédula u otros identificadores personales como código.
5. Permitir desactivar, rotar o reemplazar el código ante pérdida o sospecha de uso indebido. Mostrarlo solo a usuarios autorizados y no guardarlo en bitácoras de acceso general.
6. Registrar `Method = FixedCode`, terminal, fecha/hora de servidor y el código de empleado resuelto. Si se repiten marcas incompatibles, generar incidencia en lugar de modificar registros anteriores.
7. La empresa puede configurar si la terminal pide seleccionar explícitamente `Entrada`/`Salida` o si Koape propone la acción siguiente. El modo automático debe validar la secuencia y permitir revisión de anomalías.
8. En la configuración de empresa debe mostrarse una advertencia: el código fijo es práctico, pero puede compartirse; para una comprobación de presencia más fuerte, preferir QR temporal desde sesión autenticada o un lector con control adicional.

### Modalidad C — Importación de archivo CSV predefinido
1. Un usuario autorizado sube un archivo CSV con el formato preconfigurado para la empresa/equipo.
2. El sistema importa las marcas según el perfil de columnas y formato guardado.
3. En esta modalidad no se realiza verificación interactiva de identidad del empleado en el momento de marcar: el archivo se considera la fuente de registros entregada por el operador.
4. Aunque no se compruebe identidad en vivo, sí se deben realizar controles técnicos mínimos: formato, columnas requeridas, fechas/horas válidas, empresa, códigos de empleado reconocibles, tamaño, duplicados, rango de fechas y errores de lectura. Las filas problemáticas deben informarse; nunca asignarlas por aproximación.
5. Debe poder activarse un perfil **CSV confiado / sin verificación presencial**, con aviso explícito de que se omite la verificación de presencia. No confundir esa opción con desactivar validaciones de datos o auditoría.
6. Mantener staging, previsualización, resumen y confirmación antes de guardar, salvo que un proceso automatizado previamente autorizado tenga una política de importación documentada.
7. Guardar quién subió el archivo, fecha/hora, hash/checksum, perfil utilizado, rango de fechas, filas aceptadas/rechazadas y resultado. Reimportar el mismo archivo no debe duplicar marcas.
8. La fuente debe quedar identificada como `CSVImport`; no aparentar que las marcas fueron capturadas por QR o código fijo.

### Entidades y campos adicionales

**`AttendanceTerminal`**
- `internalId` PK
- `CompanyId` FK
- `TerminalCode` único por empresa
- `Name`, `Location`, `TerminalType` (`QRReader`, `FixedCode`, `Hybrid`, `ImportStation`)
- `AllowedMethods` / configuración equivalente
- `DeviceSecretHash` o credencial administrada de forma segura; nunca almacenar secretos en texto plano
- `TimeZoneId`, `IsActive`, `LastSeenAt`
- `CreatedAt`, `CreatedBy`, `UpdatedAt`, `UpdatedBy`

**`EmployeeAttendanceCredential`**
- `internalId` PK
- `CompanyId`, `EmployeeId`
- `AttendanceCode` (código fijo; guardar con protección apropiada y evitar exponerlo en listados generales)
- `CodeVersion`, `ValidFrom`, `ValidTo`, `Status`, `CreatedAt`, `CreatedBy`, `RevokedAt`, `RevokedBy`
- `UNIQUE(CompanyId, AttendanceCode)` para credenciales activas, implementado con el mecanismo compatible con la base de datos.

**`AttendanceQrToken`**
- `internalId` PK
- `CompanyId`, `EmployeeId`
- `TokenHash` (guardar hash del token, no el token en claro)
- `RequestedAt`, `ExpiresAt`, `ConsumedAt`, `CancelledAt`
- `RequestedByUserId`, `Status`, `TerminalId` nullable, `RequestSessionId` o identificador seguro de sesión
- `AttemptCount`, `LastAttemptAt`, `LastFailureReason`
- índice por `TokenHash`, `ExpiresAt`, `Status`; política de expiración/limpieza segura.

**Campos a añadir a `AttendancePunch`**
- `Method` (`QR`, `FixedCode`, `CSVImport`, `Manual`, `API`)
- `AttendanceTerminalId` nullable
- `CredentialId` nullable
- `QrTokenId` nullable
- `VerificationLevel` (`AuthenticatedTemporaryQR`, `FixedCodeOnly`, `ImportedFile`, `ManualApproved`, `ExternalDevice`)
- `CaptureReference` nullable

**Campos a añadir a `AttendanceImportBatch`**
- `ImportMode` (`PredefinedCSV`, `ExternalClockCSV`, `TrustedCSV`)
- `IdentityCheckPerformed` boolean, normalmente `false` para CSV
- `ImportPolicyVersion` y `OperatorNotes` opcionales.

### Endpoints/servicios lógicos requeridos
Adaptar a las rutas y convenciones reales de Koape; estos son nombres lógicos, no rutas obligatorias:
- `RequestAttendanceQr`: requiere sesión del empleado; genera QR temporal.
- `CancelAttendanceQr`: cancela un token no consumido.
- `RegisterAttendanceQrPunch`: terminal autenticada presenta token; valida y consume de forma atómica.
- `RegisterAttendanceFixedCodePunch`: terminal autorizada presenta código fijo y acción entrada/salida.
- `PreviewAttendanceCsv`: parsea el archivo y devuelve resumen sin guardar marcas finales.
- `CommitAttendanceCsv`: confirma lote validado de forma transaccional e idempotente.

### Seguridad, privacidad y concurrencia
- Usar HTTPS en todos los flujos.
- QR temporal: token criptográficamente aleatorio, uso único, vigencia corta y hash almacenado; nunca un QR permanente con datos personales.
- Aplicar rate limiting a solicitudes QR y códigos fijos; bloquear/alertar intentos repetidos.
- Validar terminal y empresa en backend, no solo desde la UI.
- El consumo del token QR debe ser atómico para impedir dos marcas concurrentes.
- Guardar hora de servidor en UTC o con una política temporal consistente y presentar hora local según zona de la empresa.
- Definir política de retención de tokens, registros de acceso y datos de asistencia.
- No recoger geolocalización o biometría por defecto; solo añadirlas con decisión expresa, base legal y revisión de privacidad.
- La modalidad CSV omite comprobación presencial, pero no omite integridad de datos, deduplicación ni trazabilidad.

### Criterios de aceptación específicos
- Empleado autenticado solicita QR temporal y el lector registra una única marca válida.
- QR vencido, reutilizado o perteneciente a otra empresa es rechazado.
- Un código fijo válido registra una marca desde una terminal autorizada; un código desconocido no registra nada.
- Repeticiones incoherentes generan incidencia y no borran ni sobrescriben marcas.
- CSV predefinido puede importarse sin verificación presencial, dejando explícita la fuente y el operador.
- CSV duplicado no crea marcas repetidas; errores pueden descargarse y corregirse.
- Cada marca permite conocer el método de captura, terminal, empresa, empleado, fecha/hora y referencia de auditoría.

## 7. Motor de asistencia
- Usar horario, contrato y régimen vigentes en la fecha, no los actuales.
- Distinguir trabajado, pausas, tardanza, salida anticipada, ordinario, horas extra candidatas, nocturnidad, feriados y ausencias.
- Marca no significa automáticamente hora extra pagable; exigir autorización/regla documentada.
- Permitir múltiples tramos diarios y turnos nocturnos/cruce de medianoche.
- Cambios a períodos cerrados generan versión/ajuste.
- Toda regla automática debe ser visible, explicable y auditable.

## 8. Motor de nómina y costo patronal
- Reproducible: mismos datos y versión de reglas generan el mismo resultado.
- Toda línea debe indicar concepto, base, cantidad, tasa, importe, origen, regla aplicada y explicación.
- Separar haberes, descuentos, aportes del trabajador, aportes patronales e informativos.
- La frecuencia de pago se separa de la base de remuneración.
- Recargos, topes, mínimos, aportes y bases se obtienen de reglas versionadas, nunca de constantes.
- No aplicar descuentos sin autorización/base legal; validar límites configurados.
- Anticipos/préstamos deben tener desembolso, saldo, recuperación y evitar doble descuento.
- Aguinaldo: detalle anual de remuneraciones computables enlazado a líneas salariales; reglas de inclusión/exclusión versionadas.
- Vacaciones: saldo por movimientos (generado, tomado, ajuste, saldo) y tratamiento salarial según regla vigente.
- Liquidación final: calcular según causal, antigüedad, fechas, régimen y reglas aplicables; no asumir todos los conceptos para todos los casos.
- Aportes patronales se incluyen en `TotalEmployerCost`, nunca se restan del neto del empleado.
- Separar provisiones contables de pagos/costos reales para evitar doble conteo.
- Redondeo centralizado y documentado. Recalcular no duplica conceptos, pagos ni novedades.
- Bloquear aprobación si faltan salario, contrato, reglas legales esenciales o validaciones críticas.

## 9. Marco legal paraguayo
Implementar reglas parametrizadas y versionadas por vigencia. Fuentes oficiales a verificar antes de producción:
- Código del Trabajo, Ley N.º 213/93 y modificatorias (BACN).
- MTESS: salario mínimo, vacaciones, REOP, libros laborales, liquidación y obligaciones.
- IPS: aportes, bases, regímenes, topes y excepciones.
- Normativa vigente de licencias, reposos, maternidad/paternidad, accidentes y seguridad laboral.

Dato inicial a verificar antes de activar: se reportó para julio de 2026 un salario mínimo general de referencia de G. 3.044.000/mes y jornal de G. 117.077 para actividades diversas no especificadas. No tratarlo como universal: validar categoría, régimen y resolución oficial. También verificar tasas IPS, recargos, vacaciones y bases computables con fuentes oficiales y revisión laboral-contable. Toda regla debe guardar fuente, fecha de vigencia, aprobador y pruebas. Si no se verificó, mantenerla en estado `Draft/NeedsReview` y bloquear liquidación real dependiente de ella.

## 10. Pantallas y flujos
Menú: Panel RR. HH.; Empleados; Contratos; Historial salarial; Departamentos/puestos/centros de costo; Horarios/turnos; Dispositivos y perfiles CSV; Importar marcaciones; Asistencia; Incidencias/horas extra; Permisos/vacaciones; Conceptos salariales; Anticipos/préstamos; Períodos; Calcular/revisar/aprobar nómina; Pagos/recibos; Aguinaldo; Liquidación final; Costo patronal; Reportes; Parámetros legales; Auditoría/importaciones.

**Flujo CSV:** elegir empresa/reloj/perfil/archivo → previsualizar → mapear columnas → validar → corregir códigos → confirmar → guardar marcas → recalcular asistencia abierta → descargar rechazos y resumen.
**Flujo nómina:** abrir período → verificar contratos/salarios/asistencia/novedades/reglas → simular → revisar advertencias y diferencias → aprobar → cerrar → registrar pagos → emitir recibos. Rectificar mediante corrida vinculada.

## 11. Permisos
Adaptar al RBAC existente, con permisos equivalentes a:
- `HR.Employee.View/Create/Edit/Terminate`
- `HR.Contract.View/Create/Edit/Approve`
- `HR.Salary.View/Edit/Approve`
- `HR.Attendance.View/Import/Adjust/Approve`
- `HR.Leave.View/Request/Approve`
- `HR.Payroll.View/Calculate/Approve/Close/Reopen/Rectify`
- `HR.Payment.Register/Confirm`
- `HR.Payslip.View/Issue/Void`
- `HR.Advance.Request/Approve/Pay`
- `HR.LegalRules.View/Edit/Approve`
- `HR.EmployerCost.View/Export`
- `HR.Compliance.Prepare/Export/ConfirmSubmission`
- `HR.Audit.View`

Validar permisos y empresa en cada endpoint/servicio. Restringir cuentas bancarias y certificados médicos. Separar operador/aprobador cuando la política lo exija. Reabrir/cerrar exige motivo. No borrar auditoría.

## 11 bis. Perfiles de acceso obligatorios

Implementar control de acceso por roles (RBAC) en interfaz y, obligatoriamente, en backend/API/servicios. Los tres perfiles iniciales son **Administrador**, **Gestor de RR. HH.** y **Empleado**. Deben ser roles asignables por usuario, con alcance por empresa y sucursal; si el repositorio ya tiene usuarios, roles y permisos, extenderlos sin duplicar el sistema de identidad. Aplicar denegación por defecto y registrar las operaciones relevantes en la bitácora.

### Perfil 1 — Administrador
- Puede ver y operar todos los módulos y datos autorizados de las empresas y sucursales que administra.
- Puede crear, editar, activar y desactivar usuarios; asignar perfiles y alcance por empresa/sucursal.
- Puede dar de alta, editar datos operativos y dar de baja/inactivar empleados. La baja debe ser lógica y conservar legajo, movimientos, documentos, nóminas y auditoría.
- Puede crear, editar, activar y desactivar empresas y sucursales según el alcance administrativo de su cuenta. La baja de empresa/sucursal será lógica y no eliminará historia.
- Puede acceder a configuraciones, parámetros del módulo, terminales, credenciales de marcación, perfiles CSV y permisos.
- Puede gestionar liquidaciones y movimientos, sujeto a las reglas de cierre y trazabilidad.
- **Límite obligatorio:** no puede modificar ni borrar registros históricos cerrados/inmutables (por ejemplo, nóminas cerradas, recibos emitidos, períodos cerrados, marcaciones consolidadas o liquidaciones finales cerradas). Para corregirlos debe utilizar un flujo explícito de rectificación/reapertura autorizado, con motivo obligatorio, permisos específicos, vínculo al registro original, conservación de la versión anterior y auditoría. Si la política no habilita ese flujo, debe solicitarse una rectificación formal; nunca sobrescribir el histórico.

### Perfil 2 — Gestor de RR. HH.
- Puede consultar empleados, contratos, horarios, asistencia, movimientos y novedades dentro de las empresas/sucursales asignadas.
- Puede cargar, corregir en períodos abiertos y revisar movimientos: ausencias, permisos, vacaciones, horas extra, bonos, comisiones, descuentos, anticipos, préstamos y demás conceptos permitidos.
- Puede importar archivos CSV y cargar/ajustar lecturas de horas o marcaciones cuando la empresa utilice esa modalidad. Debe quedar identificado quién cargó o corrigió cada dato y por qué.
- Puede preparar, calcular, revisar y generar liquidaciones de nómina, aguinaldo y liquidación final, y emitir/consultar recibos según los permisos asignados. El cierre/aprobación final debe seguir la política de aprobación configurada; no asumir que calcular equivale a aprobar o pagar.
- Puede consultar reportes operativos y de nómina según su alcance.
- **No puede:** crear, editar administrativamente, activar/desactivar ni dar de baja usuarios; dar de alta o baja empresas o sucursales; dar de alta o baja empleados; administrar roles/permisos; entrar ni modificar configuraciones globales, parámetros legales, credenciales de API o ajustes de seguridad. Tampoco puede sobrescribir históricos cerrados ni borrar auditoría.

### Perfil 3 — Empleado
- Solo puede acceder a su propia ficha visible para el empleado, sus horarios, marcaciones, asistencia, permisos/solicitudes, vacaciones, movimientos personales autorizados, liquidaciones y recibos de sueldo publicados.
- No puede consultar información de otros empleados, reportes generales, datos de otras empresas/sucursales ni datos administrativos confidenciales. El alcance personal se obtiene del usuario autenticado en el servidor; no confiar en un `EmployeeId` enviado por el navegador.
- No puede editar directamente su legajo, salario, movimientos, marcaciones, liquidaciones, recibos ni datos históricos. Las solicitudes (por ejemplo, permiso, vacaciones o corrección de marca) se registran como solicitudes pendientes, no como cambios efectivos hasta ser procesadas por un perfil autorizado.
- Puede solicitar un QR temporal de asistencia desde su sesión móvil si está habilitada esa modalidad. El empleado no puede crear, renovar manualmente, reutilizar ni validar por sí mismo la marca: el backend genera el token y solo el lector/terminal autorizado confirma el registro. Si se habilita código fijo, el empleado puede consultar el código solo según la política definida; nunca puede administrar códigos ajenos.
- Puede ver el estado y resultado de sus solicitudes y las confirmaciones de sus propias marcaciones.

### Matriz resumida
| Capacidad | Administrador | Gestor RR. HH. | Empleado |
|---|---|---|---|
| Ver datos generales de RR. HH. | Sí, según alcance | Sí, según alcance | No; solo propios |
| Crear/editar/activar usuarios y asignar roles | Sí | No | No |
| Alta/baja lógica de empleados | Sí | No | No |
| Alta/baja lógica de empresas/sucursales | Sí, según alcance | No | No |
| Configuración global, seguridad y reglas legales | Sí, con auditoría | No | No |
| Cargar novedades/movimientos | Sí | Sí, períodos abiertos | No; solo solicita |
| Importar CSV/cargar lecturas de horas | Sí | Sí | No |
| Calcular/generar liquidaciones | Sí | Sí | No |
| Aprobar/cerrar/pagar nómina | Según permisos y política | Solo si se concede permiso explícito | No |
| Consultar recibos de sueldo | Sí, según alcance | Sí, según alcance | Solo propios publicados |
| Solicitar QR temporal propio | No aplica como empleado, salvo cuenta dual explícita | No aplica como empleado, salvo cuenta dual explícita | Sí |
| Modificar/borrar histórico cerrado directamente | No | No | No |
| Rectificar/reabrir histórico con flujo auditado | Solo permiso explícito y motivo | Solo si se concede permiso explícito | No |

### Reglas técnicas de autorización
1. Definir permisos atómicos, por ejemplo `HR.User.Manage`, `HR.Company.Manage`, `HR.Branch.Manage`, `HR.Employee.Create`, `HR.Employee.Terminate`, `HR.Settings.Manage`, `HR.Movement.Create`, `HR.Attendance.Import`, `HR.Attendance.Adjust`, `HR.Payroll.Calculate`, `HR.Payroll.Approve`, `HR.Payroll.Close`, `HR.Payroll.Reopen`, `HR.History.Rectify`, `HR.Payslip.ViewOwn`, `HR.Attendance.Qr.RequestOwn`. Asignarlos a los tres roles iniciales sin impedir futuras personalizaciones controladas.
2. Aplicar autorización en cada endpoint, consulta, comando, descarga, exportación y acción de interfaz. Ocultar botones no reemplaza la validación del servidor.
3. Aplicar aislamiento por empresa/sucursal y propiedad del empleado en cada lectura y escritura. Probar intentos de acceso cambiando IDs en URL, cuerpo, filtros y exportaciones.
4. Separar permisos de calcular, aprobar, cerrar, pagar, reabrir y rectificar. No concederlos implícitamente por tener acceso general.
5. Mantener registros cerrados inmutables. Las rectificaciones se guardan como nuevas versiones/transacciones relacionadas, con usuario, fecha/hora del servidor, motivo, valores previos/nuevos y aprobador cuando corresponda. No eliminar registros de auditoría.
6. La asignación de perfiles y alcance solo puede realizarla un administrador autorizado. Evitar que un administrador se eleve privilegios a sí mismo fuera de la política de seguridad; auditar cambios de roles y permisos.
7. Si una persona necesita desempeñar más de un rol, permitir múltiples roles únicamente por asignación administrativa explícita; aplicar la unión de permisos concedidos y conservar el alcance por empresa/sucursal. No convertir automáticamente una cuenta de empleado en administrador.
8. Añadir pruebas automatizadas para los tres perfiles, acceso cruzado entre empleados/empresas, intentos de alta/baja por Gestor, acceso a configuración por Gestor, edición de históricos cerrados por todos los perfiles y solicitud/consumo de QR propio.

## 12. Reportes mínimos
Legajo; contratos por vencer; nómina por empleado/concepto/centro de costo; resumen de haberes/descuentos/netos/aportes; costo patronal por empresa/sucursal/departamento/centro de costo; horas trabajadas, tardanzas, ausencias, nocturnidad, horas extra candidatas/aprobadas; marcas faltantes; vacaciones; base y cálculo de aguinaldo; anticipos/préstamos/saldos; liquidación final; cambios salariales; lotes CSV y errores; información preparada para libros/obligaciones oficiales. Exportar PDF/XLSX/CSV según capacidades existentes y aplicar permisos/filtros. Proteger CSV injection.

## 13. Pruebas obligatorias
**CSV:** coma/punto y coma; encabezado/no encabezado; UTF-8/Latin-1; fecha+hora y columnas separadas; fechas ambiguas; marcas fuera de orden; cruce de medianoche; código desconocido; empleado inactivo; fila inválida; duplicados; reimportación idempotente; lote parcialmente válido; corrección aprobada; intento de reversión sobre nómina cerrada.
**Nómina:** mensual completo; alta/baja en período; salario por hora/jornal/semanal/quincenal/mensual; comisión/bono; ausencias pagadas/no pagadas; extra aprobada/no aprobada; nocturnidad/feriado; vacaciones; aguinaldo; anticipo/préstamo; régimen especial; mínimo por categoría; aportes trabajador/patrono separados; redondeo; cierre; rectificación; concurrencia; acceso indebido por ID de otra empresa.
Los resultados esperados deben derivarse de una matriz legal aprobada, no de valores inventados.

## 14. Entregables de Claude
1. Diagnóstico de arquitectura y mapa de archivos.
2. Modelo relacional, migraciones seguras/reversibles, índices, FKs y restricciones.
3. Servicios/backend/endpoints y autorización.
4. Pantallas funcionales según UI Koape.
5. Importador CSV con perfiles, staging, preview, deduplicación, errores y rollback seguro.
6. Motor de asistencia, novedades y aprobaciones.
7. Motor de nómina explicable y reglas versionadas.
8. Aportes patronales/costo patronal y asignación a centros de costo.
9. Recibos PDF, aguinaldo, vacaciones, liquidación final y reportes.
10. Pruebas unitarias/integración/permisos; datos ficticios.
11. Documentación de instalación, operación, perfiles CSV, parámetros legales y despliegue/reversión.
12. Lista de decisiones pendientes y resultados reales de pruebas.

### Criterios de aceptación
- Alta de empleado, contrato, salario y horario con vigencia.
- Importación CSV con preview, mapeo, validación, confirmación y reporte de errores.
- Reimportar archivo no duplica marcas.
- Asistencia señala incidencias sin inventar marcas.
- Nómina puede simularse, revisarse, aprobarse y cerrarse.
- Cada línea tiene explicación y regla aplicada.
- Costo patronal se distingue del neto.
- Recibos/reportes respetan permisos.
- Cambios legales no alteran nóminas cerradas.
- Aislamiento multiempresa y auditoría comprobados.
- Pruebas ejecutadas y resultados informados con veracidad.

## 15. Prompt de arranque para Claude
Actúa como constructor del módulo RR. HH. de Koape. Empieza por Fase 0: inspecciona el repositorio, tecnología, tablas existentes, multiempresa, permisos, auditoría y definiciones XML. Presenta diagnóstico y plan antes de cambios de alto impacto. Implementa por fases usando las convenciones reales y `internalId` como PK cuando corresponda. No dupliques entidades comunes, no hardcodees reglas legales y no modifiques nóminas cerradas silenciosamente. Implementa también el marcador propio de Koape con tres métodos claramente diferenciados: (A) QR temporal solicitado desde la sesión móvil autenticada y leído por una terminal autorizada; (B) código fijo de empleado desde una terminal autorizada, aclarando que no verifica por sí solo la identidad; y (C) CSV predefinido sin verificación presencial, pero con validación técnica, deduplicación y auditoría. El importador CSV debe tener staging, preview, validación, deduplicación e informe de errores. El sistema debe ser funcional, transaccional, seguro y probado; no declares listo lo que no se haya implementado y probado. Si una cuestión legal no está verificada, deja el parámetro pendiente de aprobación y bloquea el cálculo real que dependa de ella. Al finalizar cada fase, informa archivos modificados, migraciones, pruebas ejecutadas, resultados y pendientes.
