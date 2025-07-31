# 🔧 Git Configuration Options

O Sentry Solver oferece opções avançadas de personalização para o gerenciamento Git. Configure essas opções no arquivo `.env`.

## 📝 Configurações Disponíveis

### **Branch Configuration**

#### `SENTRY_SOLVER_GIT_BRANCH_PREFIX`
- **Padrão**: `sentry-fix`
- **Descrição**: Prefixo para nomes de branches
- **Exemplo**: `hotfix`, `bugfix`, `auto-fix`

#### `SENTRY_SOLVER_GIT_INCLUDE_ISSUE_ID`
- **Padrão**: `true`
- **Descrição**: Incluir ID do issue Sentry no nome da branch
- **Resultado**: `sentry-fix-12345-badrequest-20240730-1430`

#### `SENTRY_SOLVER_GIT_INCLUDE_TIMESTAMP`
- **Padrão**: `true`
- **Descrição**: Incluir timestamp no nome da branch
- **Formato**: `YYYYMMDD-HHMM`

### **Commit Configuration**

#### `SENTRY_SOLVER_COMMIT_MESSAGE_PREFIX`
- **Padrão**: `fix`
- **Descrição**: Prefixo para mensagens de commit
- **Opções**: `fix`, `hotfix`, `bugfix`, `auto`, `sentry`

#### `SENTRY_SOLVER_COMMIT_MESSAGE_FORMAT`
- **Padrão**: `conventional`
- **Opções**:
  - `simple`: Apenas título do commit
  - `conventional`: Título + detalhes básicos
  - `detailed`: Título + explicação completa + mudanças de código

### **Push & PR Configuration**

#### `SENTRY_SOLVER_GIT_AUTO_PUSH`
- **Padrão**: `true`
- **Descrição**: Push automático para repositório remoto

#### `SENTRY_SOLVER_GIT_CREATE_PR`
- **Padrão**: `false`
- **Descrição**: Criar Pull Request automaticamente (requer GitHub CLI)

## 🌟 Exemplos de Configuração

### Configuração Minimalista
```env
SENTRY_SOLVER_GIT_BRANCH_PREFIX=fix
SENTRY_SOLVER_GIT_INCLUDE_TIMESTAMP=false
SENTRY_SOLVER_COMMIT_MESSAGE_FORMAT=simple
SENTRY_SOLVER_GIT_AUTO_PUSH=false
```
**Resultado**:
- Branch: `fix-12345-badrequest`
- Commit: `fix: BadRequestException in LogHelper.php`

### Configuração Detalhada
```env
SENTRY_SOLVER_GIT_BRANCH_PREFIX=sentry-hotfix
SENTRY_SOLVER_GIT_INCLUDE_TIMESTAMP=true
SENTRY_SOLVER_GIT_INCLUDE_ISSUE_ID=true
SENTRY_SOLVER_COMMIT_MESSAGE_FORMAT=detailed
SENTRY_SOLVER_GIT_AUTO_PUSH=true
```
**Resultado**:
- Branch: `sentry-hotfix-12345-badrequest-20240730-1430`
- Commit: Mensagem completa com explicação e código

### Configuração Corporativa
```env
SENTRY_SOLVER_GIT_BRANCH_PREFIX=auto-resolve
SENTRY_SOLVER_COMMIT_MESSAGE_PREFIX=chore
SENTRY_SOLVER_COMMIT_MESSAGE_FORMAT=conventional
SENTRY_SOLVER_GIT_CREATE_PR=true
```
**Resultado**:
- Branch: `auto-resolve-12345-badrequest-20240730-1430`
- Commit: `chore: BadRequestException in LogHelper.php`
- PR criado automaticamente

## 📋 Formatos de Commit

### Simple
```
fix: BadRequestException in LogHelper.php
```

### Conventional
```
fix: BadRequestException in LogHelper.php

- Fixed error error in app/Helpers/LogHelper.php:42
- Issue ID: 12345
- Occurrences: 15
- Confidence: 85.0%

Sentry Issue: https://sentry.io/issues/12345/
```

### Detailed
```
fix: BadRequestException in LogHelper.php

- Fixed error error in app/Helpers/LogHelper.php:42
- Issue ID: 12345
- Occurrences: 15
- Confidence: 85.0%

## Fix Details
The error occurs when trying to write logs to Google Cloud Platform.
Added proper error handling and fallback logging.

## Code Changes
Original:
logs('gcp')->error($message, $context);

Fixed:
try {
    logs('gcp')->error($message, $context);
} catch (\Exception $e) {
    \Log::error('GCP logging failed', $context);
}

Sentry Issue: https://sentry.io/issues/12345/
```

## 🎯 Casos de Uso

### Desenvolvimento Local
```env
SENTRY_SOLVER_GIT_AUTO_PUSH=false
SENTRY_SOLVER_COMMIT_MESSAGE_FORMAT=simple
```

### CI/CD Pipeline
```env
SENTRY_SOLVER_GIT_AUTO_PUSH=true
SENTRY_SOLVER_GIT_CREATE_PR=true
SENTRY_SOLVER_COMMIT_MESSAGE_FORMAT=conventional
```

### Auditoria/Compliance
```env
SENTRY_SOLVER_COMMIT_MESSAGE_FORMAT=detailed
SENTRY_SOLVER_GIT_INCLUDE_ISSUE_ID=true
SENTRY_SOLVER_GIT_INCLUDE_TIMESTAMP=true
```