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
| DI FA AS IO |  |
| System Feature Test Concept |  |

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
| Document date | xx.xx.202x |
| Protection class | Confidential |
| Author |  |
| File name |  |

Approval:

|  |  |  |  |
| --- | --- | --- | --- |
| **Role / Function** | **Name** | **Department** | **Signature** |
| Function Owner |  | DI FA SEA … |  |
| System Architect |  | DI FA SEA … |  |
| Test Architect |  | DI FA SEA … |  |

Change Log:

|  |  |  |  |  |
| --- | --- | --- | --- | --- |
| **Version** | **Date** | **Author** | **Status** | **Change Comment** |
| 0.1 | 202X-XX-XX |  | Draft | Initial draft version. |
|  |  |  |  |  |
|  |  |  |  |  |

Content

[1. General 4](#_Toc209514208)

[1.1 Compact feature description 4](#_Toc209514209)

[1.2 Relation to other Features 4](#_Toc209514210)

[1.3 Documents hierarchy 4](#_Toc209514211)

[1.4 Test roles 4](#_Toc209514212)

[1.5 Intended use in products 5](#_Toc209514213)

[1.6 Test process 5](#_Toc209514214)

[1.7 Notes for Test concept creators / readers 5](#_Toc209514215)

[2. Test strategy 6](#_Toc209514216)

[2.1 Test objectives 6](#_Toc209514217)

[2.2 Product specific derivations 6](#_Toc209514218)

[2.3 Test methods 6](#_Toc209514219)

[2.4 Test automation 6](#_Toc209514220)

[2.5 Defect tracking 6](#_Toc209514221)

[2.6 Related features 6](#_Toc209514222)

[3. Test environment 7](#_Toc209514223)

[4. Test responsibilities 8](#_Toc209514224)

[5. Test coverage 8](#_Toc209514225)

[6. Test procedure 8](#_Toc209514226)

[6.1 White box tests 8](#_Toc209514227)

[6.1.1 Preconditions 8](#_Toc209514228)

[6.1.2 Test environment 9](#_Toc209514229)

[6.1.3 Test approach 9](#_Toc209514230)

[6.1.4 Test measures 9](#_Toc209514231)

[6.1.5 Test automation 9](#_Toc209514232)

[6.1.6 Completion criteria 9](#_Toc209514233)

[6.2 Gray box tests 10](#_Toc209514234)

[6.2.1 Incrementation steps 10](#_Toc209514235)

[6.2.2 Completion criteria 11](#_Toc209514236)

[6.3 Black box tests 12](#_Toc209514237)

[6.3.1 Preconditions 12](#_Toc209514238)

[6.3.2 Test environment 12](#_Toc209514239)

[6.3.3 Test automation 12](#_Toc209514240)

[6.3.4 Test approach 12](#_Toc209514241)

[6.3.5 Function tests 13](#_Toc209514242)

[6.3.6 Engineering tests 14](#_Toc209514243)

[6.3.7 Performance tests 15](#_Toc209514244)

[6.3.8 Security tests 16](#_Toc209514245)

[6.3.9 Conformance tests 17](#_Toc209514246)

[6.3.10 Configuration tests 18](#_Toc209514247)

[6.3.11 Completion criteria 19](#_Toc209514248)

[6.3.12 Compatibility test 19](#_Toc209514249)

[7. Appendix 20](#_Toc209514250)

[7.1 Terms/Abbreviations 20](#_Toc209514251)

[7.2 Referenced Documents 20](#_Toc209514252)

<a id="_Toc209514208"></a>
# 1. General

This document describes the strategies and concepts how to test the feature xxx. It focuses on the feature level and defines test scenarios that are abstracted from the product view. This means, this document forms the basis for product-specific test specifications. To test and validate the functionality in the scope of a product, a test plan with specific test cases and test sequences need to be derived from the abstracted scenarios described here.

Thus, this document is targeted to be read by test architects and test experts that are responsible for releasing firmware for products of the AS IO ecosystem as well as to developers who implement this feature.

<a id="_Toc209514209"></a>
## 1.1 Compact feature description

*Short description of the feature in test scope.*

To understand the feature in more detail it is recommended to read the following documents in advance:

* */SPH xxx/*
* */Feature Specification /*
* *…*
<a id="_Toc209514210"></a>
## 1.2 Relation to other Features
* *Please link here related features if their test concepts exist*
<a id="_Toc209514211"></a>
## 1.3 Documents hierarchy

This document utilizes information from various sources and is embedded into a document hierarchy. The relations between those documents are depicted in the following diagram:

![Ein Bild, das Text, Screenshot, Diagramm, Schrift enthält.  KI-generierte Inhalte können fehlerhaft sein.](images/Test_Concept_Template.docx_image_001.png)

1. Figure 2: Documents hierarchy
<a id="_Toc209514212"></a>
## 1.4 Test roles

<a id="_Toc209514216"></a>
# 2. Test strategy

*If adaptions are necessary, describe this here with the specific* */Test Roles/*: *and their responsibilities:*

* *Role A*
* *Role B*
* *..*

*Otherwise delete the italic part.*

<a id="_Toc209514213"></a>
## 1.5 Intended use in products

*Realize a matrix with mapping from feature to product families/types in a dedicated document. Refer to this document here.

For now, list products here, which intend to use the feature:*

<a id="_Toc209514214"></a>
## 1.6 Test process

The general process to follow to test a feature is described in the general DI FA AS IO */test strategy/* (Add Link to overarching document).

*If deviations from the process are required to test feature xxx, describe and justify them in the following chapters.*

<a id="_Toc209514215"></a>
## 1.7 Notes for Test concept creators / readers

*Naturally, depending on your own professional background, it can be difficult to define all relevant details for each test level on your own. Nevertheless, this document aims to give an overview and a guideline for all testing activities within the product development process. Therefore, consider the creation of a feature test concept to be a team effort and do not hesitate to contact and involve experts from different / other development levels, so they can also contribute their expertise.*

*Use notes with time stamps for the open topics to provide information for the reader that some topic is not decided or could change in the future, e.g.:*

***2025-09: The RSI protocol will be replaced by the SXP protocol.***

*Test cases derived from the test concept should be based on the test case* [*guideline*](https://example.invalid/wiki/test-case-guideline) *created by the X-SEA test modularization group.*

1. Test strategy
<a id="_Toc209514217"></a>
## 2.1 Test objectives

*Describe the objective of test for this feature in detail, e.g. for Reset to Factory this could be smth. like: “The goal is to ensure, that all user specific data gets deleted, when the reset is executed”.*

<a id="_Toc209514218"></a>
## 2.2 Product specific derivations

This document describes the generic testing approaches for this feature. However, as products are different and can have additional data or special requirements, each business line must define the behavior of the feature in the scope of their products. The following topics shall be evaluated:

* **Hardware related specifics**: …
* **Product specific data**: …
* Behavior in specific scenario (e.g. FW update): …
* …
<a id="_Toc209514219"></a>
## 2.3 Test methods

*Refer to an overarching document regarding test methods (white/gray/blackbox) view.*

*If there are some specific views on test methods with respect to this feature, describe it here.*

<a id="_Toc209514220"></a>
## 2.4 Test automation

*Refer to an overarching document regarding test automation.*

*If there are some specific common feature automation aspects with respect to this feature, describe it here. All scenario specific automation shall be described in the test scenarios.*

<a id="_Toc209514221"></a>
## 2.5 Defect tracking

*Refer to an overarching document for defect tracking guidance.*

*If products deviate from this, it must be described in the corresponding test plans.*

<a id="_Toc209514222"></a>
## 2.6 Related features

*Describe the specific relations to other features here. Also describe how this influences the test concept and strategy for the feature discussed here.*

<a id="_Toc209514223"></a>
# 3. Test environment

*Refer to overarching document regarding the general test environment.*

*If you have feature specific common environment scenarios, which are valid for various test scenarios, they shall be described here.* *Specific test environments shall be described in the chapter with specific test scenarios.*

*In this chapter provide a quick overview with all required prerequisites (tooling, engineering, modified firmware, etc.), ideally already separated into the test methods / levels.*

<a id="_Toc209514224"></a>
# 4. Test responsibilities

*If your feature has a very long name on its own, consider abbreviations, when creating and naming test cases/ scenarios.*

|  |  |  |
| --- | --- | --- |
| **Test team** | **Test scenarios ID** | **Description** |
| D-Test | FEATURE\_X.TEST.DEVELOPMENT | Unit tests |
| FEATURE\_X.TEST.INCREMENTAL.1 | Component 1 |
| … | … |
| I-Test | FEATURE\_X.TEST.FUNCTION.1 | Function test 1 |
| … | … |
| S-Test | FEATURE\_X.TEST.ENGINEERING.1 | Engineering test 1 |
| … | … |
| Pen-Test | FEATURE\_X.TEST.SECURITY.1 | Security test 1 |
| … | … |

1. Table 2: Test case responsibilities

![P7441#y1](images/Test_Concept_Template.docx_image_002.png)NOTES:

Responsibility mapping is a proposal and must be decided in the product scope.

<a id="_Toc209514225"></a>
# 5. Test coverage

|  |  |  |  |
| --- | --- | --- | --- |
| **ID** | **Title** | **Source document** | **Test case** |
| #1 | … | Req.-Spec/SPH/… | FEATURE\_X.TEST.FUNCTION.1, FEATURE\_X.TEST.ENGINEERING.1,  … |
| #2 | … |  | FEATURE\_X.TEST.CONFIGURATION.2, FEATURE\_X.TEST.CONFORMANCE.1, … |
| … |  |  | … |

1. Table 3: Test case coverage of feature requirements

![P7441#y1](images/Test_Concept_Template.docx_image_003.png)NOTES:

Requirements can be taken from input requirements documents, as well derived requirements in the solution space from SPH.

<a id="_Toc209514226"></a>
# 6. Test procedure

This chapter covers different test approaches within the development process. Although of course every one of these three has their own characteristics, and good general guideline on how to structure a test case and which information to provide by it, was developed within the X-SEA modularization project and can be found here:
[X-SEA testcase guideline](https://example.invalid/wiki/test-case-guideline)

<a id="_Toc209514227"></a>
## 6.1 White box tests

Each functional unit, i.e. firmware component (see *insert reference to feature specification component overview*) shall be tested individually on development layer. For this, a suite of unit tests shall be realized to validate the correct behavior of each unit.

<a id="_Toc209514228"></a>
### 6.1.1 Preconditions

The feature specification shall be used to define the unit test independent from the implementation. However, it may be necessary to align on the unit interface as it is implemented. If the team setup and resources allow it, the test shall be implemented by a developer that did **not** implement the unit.

<a id="_Toc209514229"></a>
### 6.1.2 Test environment

A unit test framework shall be used. Since the firmware components are distributed among several firmware frameworks (IMCK, BaSy, …), the test suites defined for this feature shall be incorporated into the already existing unit test environment of the corresponding framework (e.g. *gtest*).

<a id="_Toc209514230"></a>
### 6.1.3 Test approach

Since the testable units are very dependent on the implementation, the definition of which functions inside each firmware component are to be tested is to be defined in detail in the */Feature Specification/* document.

|  |  |
| --- | --- |
| **Test case ID** | FEATURE\_X.TEST.DEVELOPMENT |
| **Automation** | Automated |

<a id="_Toc209514231"></a>
### 6.1.4 Test measures

*It is important that all corner cases are accounted for when testing the firmware units. When there are corner cases known for this feature that are not common sense, this shall be described here.*

<a id="_Toc209514232"></a>
### 6.1.5 Test automation

<a id="_Toc209514240"></a>
### 6.3.3 Test automation

<a id="_Toc209514233"></a>
### 6.1.6 Completion criteria

If there are no contradictory requirements on an upper document layer with higher priority, the following criteria shall be fulfilled:

|  |  |
| --- | --- |
| **Implementation** | For all firmware components of this feature (see /Feature Specification/) a suite of unit tests is defined and implemented. Synergies are used with existing modules of other SL/BLs. |
| **Documentation** | All test suites are documented with the *documentation-as-code* paradigm (e.g. markdown / doxygen) |
| **Code coverage** | The test suite shall realize a good *code coverage* of the feature implementation. If not > 80% can be accomplished, justifications must be documented. |
| **Automation** | The test suites shall be executed automatically in the CI pipeline. |
| **Validation** | * All test cases of all test suites are executed. * The test suites report no errors. * The test results are documented and linked to the build artifacts. |

1. Table 6: Development tests DoD

If developers decide to perform additional tests above the unit test layer, these tests shall be described, and the test result shall be documented.

<a id="_Toc209514234"></a>
## 6.2 Gray box tests

*If the feature consists of multiple firmware components that are distributed among several frameworks and are executed on different computational units:* To avoid a big bang integration, the various components shall be incrementally integrated and tested as far as possible. This requires a white box perspective of the feature as shown in *insert reference to white box view of the feature*.

<a id="_Toc209514235"></a>
### 6.2.1 Incrementation steps
       1. Component 1

In this incrementation step, … *describe incrementation step.*

* + - * 1. Preconditions
* *List preconditions to do the incrementation step*
* …
<a id="_Toc209514239"></a>
### 6.3.2 Test environment

*Describe test environment for incrementation step.*

* + - * 1. Test cases

|  |  |
| --- | --- |
| **Test case ID** | FEATURE\_X.TEST.INCREMENTAL.1 |
| **Procedure** | * Setup the test environment (see 6.2.1.1.2). * … *describe test procedure steps.* |
| **Validation** | * … *describe test validation steps.* |
| **Automation**  (optional) | Manual |

* + - 1. Component 1 -> Component 2

In this incrementation step, … *describe incrementation step.*

* + - * 1. Preconditions
* *List preconditions to do the incrementation step*
* …
  + - * 1. Test environment

*Describe test environment for incrementation step.*

* + - * 1. Test cases

|  |  |
| --- | --- |
| **Test case ID** | FEATURE\_X.TEST.INCREMENTAL.2 |
| **Procedure** | * Setup the test environment (see 6.2.1.1.2). * … *describe test procedure steps.* |
| **Validation** | * … *describe test validation steps.* |
| **Automation**  (optional) | Manual |

<a id="_Toc209514236"></a>
### 6.2.2 Completion criteria

If there are no contradicting requirements on an upper document layer with higher priority, the following criteria shall be fulfilled:

|  |  |
| --- | --- |
| **Implementation** | Product specific test cases are derived for all incrementation steps. |
| **Documentation** | All test cases are documented and filed. |
| **Validation** | All test cases are executed and validated. |
| **Automation**  (optional) | *If applicable, define which percentage of the test should be covered by automated tests or which tests need to be automated to simplify future developments.* |

1. Table 7: Incrementation tests DoD
<a id="_Toc209514237"></a>
## 6.3 Black box tests

The end-to-end functionality of the feature that the user can experience must be tested in a set of feature tests. For this, … *describe general scope of the* feature.

<a id="_Toc209514238"></a>
### 6.3.1 Preconditions

*Please enter all relevant preconditions to execute the test here.*

* + 1. Test environment

*Describe feature test environment that is generic for all following test scenarios.*

* + 1. Test automation

*Describe tools and setups required for automating the test execution of feature tests.*

<a id="_Toc209514241"></a>
### 6.3.4 Test approach

When test cases shall be conducted with combinations and variations of configuration and input data, a notation of ***OR, AND*** *and* ***XOR*** shall be used. ***OR*** is used to denote that a test is to be repeated with a different setting. ***AND*** is used to denote that the test is to be conducted with both settings enabled in a single test execution. ***XOR*** is used to denote that the test can be executed either with the one or the other setting.

Examples:

* When a test case specifies:
  + **Configuration parameter:** A***OR*** *B*
  + **Input data:** X***OR*** *Y*

the test must be conducted 4 times:

* + 1st run: **Configuration parameter** = A*,* **Input data** *= X*
  + 2nd run: **Configuration parameter** = A*,* **Input data** *= Y*
  + 3rd run: **Configuration parameter** = B*,* **Input data** *= X*
  + 4th run: **Configuration parameter** = B*,* **Input data** *= Y*
* When a test case specifies:
  + **Configuration parameter:** *A* ***XOR*** *B*
  + **Input data:** X***AND*** *Y*

the test must be conducted once, e.g.:

* 1st run*:* **Configuration parameter** = A*,* **Input data** *= X* + *Y*
<a id="_Toc209514242"></a>
### 6.3.5 Function tests
       1. Function test 1

|  |  |
| --- | --- |
| **Test case ID** | FEATURE\_X.TEST.FUNCTION.1 |
| **Description** | *Describe test case.* |
| **Requirements** | */Feature Elaboration/*: *#1*, … *add cross references to requirements in test coverage section.*  */SPH S7+ Modules Security/*: *#4.x.1*, … *add cross references to requirements in test coverage section.* |
| **Process** | * Setup the test environment … (see chapter *6.3.1*). * … *describe test procedure steps.* |
| **Validation** | * … *describe test validation steps.* |
| **Automation**  (optional) | *Manual / Automated* |

* + - 1. Function test …

|  |  |
| --- | --- |
| **Test case ID** | FEATURE\_X.TEST.FUNCTION.2 |
| **Description** | *Describe test case.* |
| **Requirements** | */Feature Elaboration/*: *#2*, … *add cross references to requirements in test coverage section.*  */SPH S7+ Modules Security/*: *#4.x.2*, … *add cross references to requirements in test coverage section.* |
| **Process** | * Setup the test environment … (see chapter *6.3.1*). * … *describe test procedure steps.* |
| **Validation** | * … *describe test validation steps.* |
| **Automation**  (optional) | *Manual / Automated* |

<a id="_Toc209514243"></a>
### 6.3.6 Engineering tests
       1. Engineering test 1

|  |  |
| --- | --- |
| **Test case ID** | FEATURE\_X.TEST.ENGINEERING.1 |
| **Description** | *Describe test case.* |
| **Requirements** | */Feature Elaboration/*: *#1*, … *add cross references to requirements in test coverage section.*  */SPH S7+ Modules Security/*: *#4.x.1*, … *add cross references to requirements in test coverage section.* |
| **Process** | * Setup the test environment … (see chapter *6.3.1*). * … *describe test procedure steps.* |
| **Validation** | * … *describe test validation steps.* |
| **Automation**  (optional) | *Manual / Automated* |

* + - 1. Engineering test …

|  |  |
| --- | --- |
| **Test case ID** | FEATURE\_X.TEST.ENGINEERING.2 |
| **Description** | *Describe test case.* |
| **Requirements** | */Feature Elaboration/*: *#2*, … *add cross references to requirements in test coverage section.*  */SPH S7+ Modules Security/*: *#4.x.2*, … *add cross references to requirements in test coverage section.* |
| **Process** | * Setup the test environment … (see chapter *6.3.1*). * … *describe test procedure steps.* |
| **Validation** | * … *describe test validation steps.* |
| **Automation** (optional) | *Manual / Automated* |

<a id="_Toc209514244"></a>
### 6.3.7 Performance tests
       1. Performance test 1

|  |  |
| --- | --- |
| **Test case ID** | FEATURE\_X.TEST.PERFORMANCE.1 |
| **Description** | *Describe test case.* |
| **Requirements** | */Feature Elaboration/*: *#1*, … *add cross references to requirements in test coverage section.*  */SPH S7+ Modules Security/*: *#4.x.1*, … *add cross references to requirements in test coverage section.* |
| **Process** | * Setup the test environment … (see chapter *6.3.1*). * … *describe test procedure steps.* |
| **Validation** | * … *describe test validation steps.* |
| **Automation**  (optional) | *Manual / Automated* |

* + - 1. Performance test …

|  |  |
| --- | --- |
| **Test case ID** | FEATURE\_X.TEST.PERFORMANCE.2 |
| **Description** | *Describe test case.* |
| **Requirements** | */Feature Elaboration/*: *#2*, … *add cross references to requirements in test coverage section.*  */SPH S7+ Modules Security/*: *#4.x.2*, … *add cross references to requirements in test coverage section.* |
| **Process** | * Setup the test environment … (see chapter *6.3.1*). * … *describe test procedure steps.* |
| **Validation** | * … *describe test validation steps.* |
| **Automation**  (optional) | Automated |

<a id="_Toc209514245"></a>
### 6.3.8 Security tests
       1. Security test 1

|  |  |
| --- | --- |
| **Test case ID** | FEATURE\_X.TEST.SECURITY.1 |
| **Description** | *Describe test case.* |
| **Requirements** | */Feature Elaboration/*: *#1*, … *add cross references to requirements in test coverage section.*  */SPH S7+ Modules Security/*: *#4.x.1*, … *add cross references to requirements in test coverage section.* |
| **Process** | * Setup the test environment … (see chapter *6.3.1*). * … *describe test procedure steps.* |
| **Validation** | * … *describe test validation steps.* |
| **Automation**  (optional) | *Manual / Automated* |

* + - 1. Security test …

|  |  |
| --- | --- |
| **Test case ID** | FEATURE\_X.TEST.SECURITY.2 |
| **Description** | *Describe test case.* |
| **Requirements** | */Feature Elaboration/*: *#2*, … *add cross references to requirements in test coverage section.*  */SPH S7+ Modules Security/*: *#4.x.2*, … *add cross references to requirements in test coverage section.* |
| **Process** | * Setup the test environment … (see chapter *6.3.1*). * … *describe test procedure steps.* |
| **Validation** | * … *describe test validation steps.* |
| **Automation**  (optional) | Automated |

<a id="_Toc209514246"></a>
### 6.3.9 Conformance tests
       1. Conformance test 1

|  |  |
| --- | --- |
| **Test case ID** | FEATURE\_X.TEST.CONFORMANCE.1 |
| **Description** | *Describe test case.* |
| **Requirements** | */Feature Elaboration/*: *#1*, … *add cross references to requirements in test coverage section.*  */SPH S7+ Modules Security/*: *#4.x.1*, … *add cross references to requirements in test coverage section.* |
| **Process** | * Setup the test environment … (see chapter *6.3.1*). * … *describe test procedure steps.* |
| **Validation** | * … *describe test validation steps.* |
| **Automation**  (optional) | *Manual / Automated* |

* + 1. Penetration tests

Penetration tests shall be executed if the capacity allows it. The concept of Fuzz-Testing shall be incorporated to improve the quality of the penetration tests. For this, tools like *Blackduck Defensics*, shall be used.

* + - 1. Penetration test 1

|  |  |
| --- | --- |
| Test case ID | FEATURE\_X.TEST.PENETRATION.1 |
| Description | Describe test case. |
| Requirements | /Feature Elaboration/: #2, … add cross references to requirements in test coverage section.  /SPH S7+ Modules Security/: #4.x.2, … add cross references to requirements in test coverage section. |
| Process | Setup the test environment … (see chapter 6.3.1).  … describe test procedure steps. |
| Validation | … describe test validation steps. |
| Automation  (optional) | Manual /Automated |

<a id="_Toc209514247"></a>
### 6.3.10 Configuration tests
       1. Configuration test 1

|  |  |
| --- | --- |
| **Test case ID** | FEATURE\_X.TEST.CONFIGURATION.1 |
| **Description** | *Describe test case.* |
| **Requirements** | */Feature Elaboration/*: *#1*, … *add cross references to requirements in test coverage section.*  */SPH S7+ Modules Security/*: *#4.x.1*, … *add cross references to requirements in test coverage section.* |
| **Process** | * Setup the test environment … (see chapter *6.3.1*). * … *describe test procedure steps.* |
| **Validation** | * … *describe test validation steps.* |
| **Automation**  (optional) | *Manual / Automated* |

* + - 1. Configuration test …

|  |  |
| --- | --- |
| **Test case ID** | FEATURE\_X.TEST.CONFIGURATION.2 |
| **Description** | *Describe test case.* |
| **Requirements** | */Feature Elaboration/*: *#2*, … *add cross references to requirements in test coverage section.*  */SPH S7+ Modules Security/*: *#4.x.2*, … *add cross references to requirements in test coverage section.* |
| **Process** | * Setup the test environment … (see chapter *6.3.1*). * … *describe test procedure steps.* |
| **Validation** | * … *describe test validation steps.* |
| **Automation**  (optional) | Manual / Automated |

<a id="_Toc209514249"></a>
### 6.3.12 Compatibility test

*If there is a predecessor, what is the solution to ensure, that the new version of the feature/ product using the feature behaves as the predecessor. Please describe all specifics necessary to achieve compatibility.*

*Please also consider compatibility with other features here.*

<a id="_Toc209514248"></a>
### 6.3.11 Completion criteria

If there are no contradictory requirements on an upper document layer with higher priority, the following criteria shall be fulfilled:

|  |  |
| --- | --- |
| **Implementation** | Product specific test cases are derived for all described generic feature test cases. |
| **Test coverage** | Derived test cases link to requirements so that the *test coverage* can be evaluated. 100% of the requirements shall be covered by the test cases. |
| **Documentation** | All test cases are documented and filed into a test management system (e.g. TMS). |
| **Validation** | All test cases are executed, and test results are filed into TFS. The results show:   * No open class 2 faults * The number of class 3 and class 4 faults is in the acceptable range of the product. |
| **Automation**  (optional) | Tests cases with automation requirements shall be automated. |

1. Table 8: Feature tests DoD

<a id="_Toc209514250"></a>
# 7. Appendix
<a id="_Toc209514251"></a>
## 7.1 Terms/Abbreviations

|  |  |
| --- | --- |
| **Term / Abbreviation** | **Explanation** |
| EU CRA | Cyber Resilience Act of the European Union |
| IM | Interface Module |
| IMC | Integration Test Modularization Council |
| PLC | Programmable Logic Controller |
| TAF | Test Automation Framework |
| TFS | Team Foundation Server |
| TFW | Test FrameWork |
| TMS | Test Management System |

<a id="_Toc209514252"></a>
## 7.2 Referenced Documents

|  |  |
| --- | --- |
| **Reference** | **Document with title, definite identifier and version** |
| /Test Roles/ | [Test\_Roles.docx](https://example.invalid/templates/test-roles.docx) |
| /Test Process/ | [Test\_Process.docx](https://example.invalid/templates/test-process.docx) |
| /Test Types/ | [Test\_Types.docx](https://example.invalid/templates/test-types.docx) |
| /SPH xxx/ | … |
| /Feature Specification yyy/ | *…* |
|  |  |
| … |  |