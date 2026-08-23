# Decision Evidence Package versioning

## English

DEP places an integer major in both schema identity (`proofline-decision-evidence-package-v1`) and directory (`v1`). A released major is immutable.

- Changing required fields, canonicalization, hash domains, node meaning, archive layout, validation meaning, or any value that can alter a valid root requires a new major and schema identity.
- Clarification, editorial correction, additional invalid vectors, or verifier hardening may remain in v1 only when they reject input already invalid under the written v1 contract.
- Consumers reject unknown majors. During a documented transition, producers should offer the previous major and must not silently rewrite exported packages.
- V1 objects are closed; experimental metadata stays outside the package until standardized in a new major.

V1 provides integrity and lineage, not signatures, authenticity, identity trust, revocation, authorization, or trusted timestamps. New trust semantics require a threat model and cannot be claimed retroactively for v1.

## Tiếng Việt

DEP đặt integer major trong cả schema identity (`proofline-decision-evidence-package-v1`) và directory (`v1`). Major đã release là immutable.

- Thay required field, canonicalization, hash domain, node meaning, archive layout, validation meaning hoặc giá trị có thể đổi valid root yêu cầu major và schema identity mới.
- Clarification, editorial correction, invalid vector bổ sung hoặc verifier hardening chỉ được giữ ở v1 khi chúng reject input vốn đã invalid theo written v1 contract.
- Consumer reject major không biết. Trong documented transition, producer nên cung cấp major trước và không được tự rewrite package đã export.
- Object v1 là closed; experimental metadata nằm ngoài package đến khi được standardize trong major mới.

V1 cung cấp integrity và lineage, không cung cấp signature, authenticity, identity trust, revocation, authorization hoặc trusted timestamp. Trust semantic mới cần threat model và không được claim retroactive cho v1.

## 日本語

DEP は schema identity (`proofline-decision-evidence-package-v1`) と directory (`v1`) の両方に integer major を置きます。Release 済み major は immutable です。

- Required field、canonicalization、hash domain、node meaning、archive layout、validation meaning、または valid root を変え得る値の変更には、新 major と schema identity が必要です。
- Clarification、editorial correction、追加 invalid vector、verifier hardening は、written v1 contract 上すでに invalid な input を reject する場合だけ v1 に追加できます。
- Consumer は unknown major を reject します。Documented transition 中は producer は previous major を提供し、export package を暗黙 rewrite してはいけません。
- V1 object は closed です。Experimental metadata は新 major で standardize されるまで package 外に置きます。

V1 が提供するのは integrity と lineage であり、signature、authenticity、identity trust、revocation、authorization、trusted timestamp ではありません。新 trust semantic には threat model が必要で、v1 に retroactive claim できません。
