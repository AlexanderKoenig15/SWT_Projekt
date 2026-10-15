---
title: Content
owner:
  - jane.doe@example.com
author:
  - jane.doe@example.com
document_version: 0.1
modified_at: "2026-08-28T12:08:29+00:00"
# Allowed values: work in progress | review version | released
state: null
comment: null
# Allowed values: C0 (frei verwendbar) | C1 (intern) | C2 (vertraulich) | C3 (streng vertraulich)
access_classification:

front_matter_revision: 20260904_1200
---


<!--
The front page of the feature specification must be created in Microsoft Word. The front page must
contain the SIEMENS corporate design and the status tracking. The two resulting PDF files must be
merged into the final feature specification document.

Required steps to create the final feature spec document:
1. [MS Word] Edit the front page with correct date, document version and document status.
2. [MS Word] Create a PDF of the front page.
3. [VS Code] Create a PDF of the feature spec content (this file) using the Markdown PDF extension.
4. [PDF Tool] Merge the two PDFs into one file.

SETUP: Workspace settings for Markdown PDF (header/footer/margins)
  Step A - Create <workspace-root>/.vscode/settings.json (once per workspace clone).
  Step B - Paste the content of the skill asset markdown-pdf-settings.json and fill the
           {{PLACEHOLDERS}} (department, project, file name, version, date, status, template id).
           Update the "Document:" field whenever the document version or date changes.
  Step C - Open this file, run Command Palette (Ctrl+Shift+P) -> "Markdown PDF: Export (pdf)".
           The PDF is saved in the same folder as this .md file.
-->

# Content

- [1. Scope](#1-scope)
- [2. General](#2-general)
  - [2.1 Brief Description](#21-brief-description)
  - [2.2 Product Structure](#22-product-structure)
  - [2.3 Structure of Product as Supplied](#23-structure-of-product-as-supplied)
- [3. Features](#3-features)
  - [3.1 Feature List](#31-feature-list)
  - [3.2 Feature Description](#32-feature-description)
    - [3.2.1 Feature Name Placeholder](#321-feature-name-placeholder)
  - [3.3 Handling of Known Error Messages](#33-handling-of-known-error-messages)
  - [3.4 System Features](#34-system-features)
  - [3.5 Hidden Features](#35-hidden-features)
  - [3.6 System Environment](#36-system-environment)
  - [3.7 Environmental Conditions and Approvals](#37-environmental-conditions-and-approvals)
- [4. Compatibility with Previous Version](#4-compatibility-with-previous-version)
  - [4.1 Interfaces](#41-interfaces)
  - [4.2 Functionality](#42-functionality)
- [5. Appendix](#5-appendix)
  - [5.1 Terms/Abbreviations](#51-termsabbreviations)
  - [5.2 Referenced Documents](#52-referenced-documents)

# 1. Scope

<!-- One short paragraph: what this specification describes, the capability/protection it provides,
and which product range it applies to. -->

# 2. General

## 2.1 Brief Description
<!-- List the product/component highlights in table format. -->

| Area | Summary | Customer Impact |
|------|---------|-----------------|
|      |         |                 |

## 2.2 Product Structure
<!-- How is the product or component configured (hardware (module), software, firmware, SW components)? -->

```
<Product Component>
├── <Area 1>
│   └── <sub-component>
└── <Area 2>
    └── <sub-component>
```

## 2.3 Structure of Product as Supplied
<!-- Designation, description, MLFB, and packaging unit of the product(s)/component(s) to be shipped
per the sales/marketing specifications. Consider all product variants. Binding specification to avoid
mismatches between the quantity unit of FDB and that of CADIM/SAP. -->

The feature specification applies to the following MLFBs.

| MLFB | Module |
|------|--------|
|      |        |

# 3. Features

## 3.1 Feature List

| Feature Area | Feature | Status |
|--------------|---------|--------|
|              |         |        |

## 3.2 Feature Description

### 3.2.1 Feature Name Placeholder

#### 3.2.1.1 Situation Up to Now
<!-- Situation up to now from the implementation perspective (weaknesses, limitations). The gap this
feature closes. -->

#### 3.2.1.2 User Objective
<!-- Reference to the specific situation (Use Case). For components, describe client usage. -->

**Use Case:**

#### 3.2.1.3 User Action
<!-- Actions the user performs; main operator control steps. For components, client actions/usage
steps. State explicitly if the feature is transparent to the user. -->

#### 3.2.1.4 System Reaction
<!-- System reaction to the user actions (abstract). Cover success and failure paths. -->

#### 3.2.1.5 User Interface
<!-- Menus, dialogs, status indicators, diagnostics and message texts. If no visible UI, state that
and list the diagnostics. -->

#### 3.2.1.6 Technical
<!-- Internal implementation details (only if no separate design document): configuration constants,
addresses, component/class names, algorithms. Optional Mermaid diagram of the mechanism. -->

#### 3.2.1.7 Documentation
<!-- State whether the feature is described in the user manual. -->

#### 3.2.1.8 System Test
<!-- How the feature is verified (bullet list of test cases). If not testable by system test, state
that and describe the Developer Test. -->

## 3.3 Handling of Known Error Messages

Not applicable for current development step.

## 3.4 System Features
<!-- Identify the system features that affect the product/component in the current development step. -->

| System Feature | Included Scope | Primary Components |
|----------------|----------------|--------------------|
|                |                |                    |

## 3.5 Hidden Features
<!-- Identify the hidden features (hidden for customers) in the current development step. Each hidden
feature uses the same 8-part subsection pattern as 3.2 (### 3.5.x <Name>). -->

## 3.6 System Environment
<!-- State the system environment, or that it is unchanged versus previous development steps. -->

## 3.7 Environmental Conditions and Approvals
<!-- Environmental conditions and approvals for the product. For SIMATIC products the Environment SPH
applies. List approvals/standards and present any deviations explicitly. -->

# 4. Compatibility with Previous Version

## 4.1 Interfaces

| Interface | Change | Compatibility |
|-----------|--------|---------------|
|           |        |               |

## 4.2 Functionality

| Feature | Previous Behavior | New Behavior |
|---------|-------------------|--------------|
|         |                   |              |

# 5. Appendix

## 5.1 Terms/Abbreviations

| Term / Abbreviation | Explanation |
|---------------------|-------------|
|                     |             |

## 5.2 Referenced Documents

| Reference | Document with title, definite identifier and version |
|-----------|------------------------------------------------------|
|           |                                                      |
