# Changelog

All notable changes to the **CRM-SDM** ontology and knowledge graph will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-08-18

### Added
- Initial public release of the **CRM-SDM** TBox ontology (OWL 2 DL) under `/ontology`.
- Instantiated Knowledge Graph ABox (54,790 triples, 192 traders, 5,568 trade flows) under `/kg/crm-sdm-kg.ttl`.
- Companion SHACL validation shape suite under `/validation/crm-sdm-shapes.ttl`.
- Operational property graph inputs and generation parameters under `/data`.
- Persistent W3ID identifier redirection setup (`https://w3id.org/crm-sdm`).
- Documentation and validation instructions in `README.md`.