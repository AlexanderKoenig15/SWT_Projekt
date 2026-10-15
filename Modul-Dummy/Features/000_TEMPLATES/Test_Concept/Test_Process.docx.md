---
title: 1. General
owner:
  - null
author:
  - null
document_version: 0.1
modified_at: "2026-08-28T12:08:29+00:00"
# Allowed values: work in progress | review version | released
state: null
comment: null
# Allowed values: C0 (frei verwendbar) | C1 (intern) | C2 (vertraulich) | C3 (streng vertraulich)
access_classification:

front_matter_revision: 20260904_1200
---

|  |  |
| --- | --- |
|  |  |
| DI FA SEA |  |
| Test Process |  |

|  |  |
| --- | --- |
| **Project / Product** | |
| Project name / version |  |
| Product name / version |  |
| Project ID |  |
| PA number |  |
| Product family | ET 200SP  ET 200MP / S71500 IO  ET 200ecoPN  ET 200clean  ET 200pro  ET 200AL  ET 200HA et al.  Coupler  PN Links |
| Path to PNB | *Reference to feature document sharepoint* |

|  |  |
| --- | --- |
| **Document** | |
| Document version | 0.1 |
| Document status | Preliminary |
| Document date | 29.07.2025 |
| Protection class | Confidential |
| Author |  |
| File name |  |

Change Log:

|  |  |  |  |  |
| --- | --- | --- | --- | --- |
| **Version** | **Date** | **Author** | **Status** | **Change Comment** |
| 0.1 | 202X-XX-XX |  | Draft | Initial draft version. |
|  |  |  |  |  |
|  |  |  |  |  |

Content

[1. General 4](#_Toc204672789)

<a id="_Toc204672789"></a>
# 1. General

![Ein Bild, das Text, Diagramm, Screenshot, Plan enthält.  KI-generierte Inhalte können fehlerhaft sein.](images/Test_Process.docx_image_001.png)

1. Figure 3: Test process
   * 1. Security feature handover

The following steps need to be followed for the handover of the security features to the business lines:

* The feature owner publishes the feature to the PL/PO of the SL/BL.
* The system architect hands over the */SPH S7+ Modules Security/* and the */Feature Specification/* to the software architects of the SL/BL. The system architect stays responsible: supporting the process, answering questions, and adapting the specification together with the software architects based on feedback.
* The test architect hands over this test concept to the test experts of the SL/BL. The test architect stays responsible: supporting the process, answering questions, and adapting the concept together with the test experts based on feedback.
  + 1. Implementation and development test planning

The following steps shall guide the planning of the feature implementation and test:

* The PL/PO of the SL/BL schedules the feature and development test implementation.
* The software architects coordinate the feature and development test implementation in the SL/BL frameworks and products with respect to the */SPH S7+ Modules Security/* and the */Feature Specification/*.
  + 1. Implementation and development testing

The following steps shall guide the implementation and development testing of the feature:

* The SL/BL development teams implement the feature based on the */SPH S7+ Modules Security/ and* */Feature Specification/*.
* The SL/BL development teams implement development tests for the features or use the ones coming with reusable components.
* The SL/BL development teams are consulted by the modularization experts to use/create synergies on the implementation and development tests.
* The SL/BL development teams integrate the tests into the CI/CD pipeline for execution and result documentation.
* Modularization experts share their knowledge over modularization coordinators with respect to reusability of firmware components and tests from/with other SL/BL.
  + 1. Integration testing

The following steps shall be followed on integration testing of the feature:

* The BL test experts derive integration test cases from this test concept in the scope of the business line.
* The BL test expert is consulted by the **modularization expert (**IMC**)** with respect to reusability of integration tests from/with other business lines.
* The BL test expert hands over the integration test plan to test development team of the business line.
* The BL test development team implements and performs the integration tests with respect to the integration test plan and documents the results.

![P7441#y1](images/Test_Process.docx_image_002.png)NOTES:

Modular Test Automation Blocks can be obtained from here [Modularization@Security.xlsx](https://example.invalid/templates/modularization-security.xlsx) (sheet *I-Test Automation Overview*) to make regression test more efficient.

* + 1. System testing

The following steps shall be followed on system testing of the feature:

* The system test modularization coordinator together with BL system test experts in the system test team derives system test cases in the product scope of the BLs with respect to reusability of system tests from/with other business lines.
* The system test team performs the tests.
* The system test team documents the test results.