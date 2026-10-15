---
title: 1. Test types
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
| Test Types |  |

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

[1. Test types 4](#_Toc204676417)

<a id="_Toc204676417"></a>
# 1. Test types

The following chapters focus on the below listed test levels and types:

* Development tests: Low level testing methods focusing on single units and source code. It includes unit testing as well as static and dynamic code analysis and can be complemented with additional test measures on development level.
* Incremental function tests: Testing methods to validate the correct functional behavior starting from a central component. Further components are successively added to avoid a big-bang integration.
* Integration tests: Integration tests can have different objectives and are thus categorized into the following subcategories:
  + Performance: Assess the speed and responsiveness of the modules under test. This typically involves evaluating processing times, throughput, and latency to ensure the modules meet operational requirements under various conditions.
  + Compatibility: Evaluate the compatibility of the module in terms of function, speed and interaction or interfaces.
  + Regression: Preliminary and final validation in case of changes to the firmware.
  + Completeness: Ensuring completeness of all consisting functions of the feature.
* Acceptance test (QA Gate): The functionality shall fulfill an acceptable level of quality, so that the functions can be operated and configured. The tests shall be coordinated and approved by the integration test but can be conducted by individual teams for the respective products.
* System tests: Feature testing to validate that the integrated functionality meets the defined functional and non-functional requirements from user perspective. The tests are carried out in a fully integrated system environment under realistic conditions to ensure that perceivable functions work as expected. System test can have different objectives and are thus categorized into the following subcategories:
  + Engineering: Test all possible valid and invalid configurations and the corresponding operation modes a user can apply.
  + Documentation: Verification that the new feature is documented in its entirety in the users documentation.
  + User acceptance: Test that all functions that can be experienced by the user fulfill the requirements.
* Performance test: Test that all non-functional requirements are fulfilled, that the feature shows the expected behavior in high load situations and that no other existing functionality is influenced by the introduction of this new feature.
* Configuration test: A specific level of testing that aims to ensure that a product works correctly under the various supported setups and environments. It complements other levels of testing, such as system testing, by focusing on the versatility and adaptability by validating correct behavior when the function is operated in the broader system scope with different device types (switches, HMI, CM / CPs, …).
* Conformance test: Test that the integrated feature conforms to all applicable standards and regulations relevant for the product in scope.
* Security test: Test that all required security measures are realized by the implementation.
* Penetration test: This test category focuses on cyber security vulnerabilities on all public interfaces of the function and must account for all known attack types (like Packet spoofing, replay attacks, eavesdropping, masquerade attacks, …).