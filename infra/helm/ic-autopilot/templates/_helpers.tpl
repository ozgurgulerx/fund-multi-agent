{{/*
Expand the name of the chart.
*/}}
{{- define "ic-autopilot.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "ic-autopilot.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "ic-autopilot.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "ic-autopilot.labels" -}}
helm.sh/chart: {{ include "ic-autopilot.chart" . }}
{{ include "ic-autopilot.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "ic-autopilot.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ic-autopilot.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Backend labels
*/}}
{{- define "ic-autopilot.backend.labels" -}}
{{ include "ic-autopilot.labels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
Backend selector labels
*/}}
{{- define "ic-autopilot.backend.selectorLabels" -}}
{{ include "ic-autopilot.selectorLabels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
Frontend labels
*/}}
{{- define "ic-autopilot.frontend.labels" -}}
{{ include "ic-autopilot.labels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Frontend selector labels
*/}}
{{- define "ic-autopilot.frontend.selectorLabels" -}}
{{ include "ic-autopilot.selectorLabels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Redis labels
*/}}
{{- define "ic-autopilot.redis.labels" -}}
{{ include "ic-autopilot.labels" . }}
app.kubernetes.io/component: redis
{{- end }}

{{/*
Redis selector labels
*/}}
{{- define "ic-autopilot.redis.selectorLabels" -}}
{{ include "ic-autopilot.selectorLabels" . }}
app.kubernetes.io/component: redis
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "ic-autopilot.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "ic-autopilot.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Backend image
*/}}
{{- define "ic-autopilot.backend.image" -}}
{{- printf "%s/%s:%s" .Values.image.registry .Values.backend.image.repository .Values.image.tag }}
{{- end }}

{{/*
Frontend image
*/}}
{{- define "ic-autopilot.frontend.image" -}}
{{- printf "%s/%s:%s" .Values.image.registry .Values.frontend.image.repository .Values.image.tag }}
{{- end }}

{{/*
Workload Identity annotations
*/}}
{{- define "ic-autopilot.workloadIdentity.annotations" -}}
{{- if .Values.azure.workloadIdentity.enabled }}
azure.workload.identity/client-id: {{ .Values.azure.workloadIdentity.clientId | quote }}
azure.workload.identity/use: "true"
{{- end }}
{{- end }}
