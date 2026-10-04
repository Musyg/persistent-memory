# Recovery and trust contract

Store source content separately from the retained authority and its freshness witness. A content snapshot may be restored only against the currently trusted authority. Opening an old store quarantines it until `restore_verify(authority.checkpoint())` reconciles it; withdrawn sources and their dependent records remain unreadable.

The authority journal, compare-and-swap version checks and idempotent operation identities reject stale publication. Rebuild projections from admissible refs; never promote an index hit directly into an answer without authority validation. Derived records must name exact parent versions through `derives`, `indexes` or `cites`. An application that omits a real dependency cannot expect transitive withdrawal of that hidden dependency.

The witness detects disagreement with an authority snapshot. It cannot detect a coordinated rollback of every trusted authority and witness. A deployment requiring that protection must retain a fresher external trust anchor. SQLite and directory durability rely on the filesystem's supported synchronization semantics. Process termination is not a simulation of every hardware or storage failure.

Core revocation is logical admissibility, not universal physical deletion. Old snapshots, external copies, logs and already displayed responses may still contain text. Applications own their retention and erasure policy. Do not store data without the required consent merely because this library supports revocation.

Run `hermes-memory-demo --directory NEW_PATH` to reproduce two independent sources, a dependent handoff, restart, withdrawal and old-content restoration. It uses entirely synthetic text and no network or model.
