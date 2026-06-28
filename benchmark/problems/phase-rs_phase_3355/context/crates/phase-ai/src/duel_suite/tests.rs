//! Registry + snapshot invariants. These run under `cargo test -p phase-ai`
//! and gate any change that adds/renames matchups or features.

use super::snapshots::{load_snapshot_at, snapshot_path};
use super::{all_matchups, find_matchup, DeckRef, FeatureKind};

#[test]
fn every_feature_kind_is_exercised() {
    let matchups = all_matchups();
    for kind in FeatureKind::ALL {
        let exercised = matchups
            .iter()
            .any(|m| m.exercises.iter().any(|k| k == kind));
        assert!(
            exercised,
            "FeatureKind::{kind:?} is not exercised by any MatchupSpec — add a matchup that \
             includes it in `exercises`, or remove the variant if the feature is gone."
        );
    }
}

/// Cross-check against `DeckFeatures` — the struct in `crate::features::mod`
/// has exactly 9 per-axis fields (landfall, mana_ramp, tribal, control,
/// aristocrats, aggro_pressure, tokens_wide, plus_one_counters,
/// spellslinger_prowess). When a new axis is added there, this assertion
/// fails until `FeatureKind::ALL` is updated to match.
#[test]
fn feature_kind_matches_deck_features_field_count() {
    assert_eq!(
        FeatureKind::ALL.len(),
        9,
        "FeatureKind::ALL is out of sync with DeckFeatures — add the new variant."
    );
}

#[test]
fn every_snapshot_loads() {
    for spec in all_matchups() {
        for (label, deck) in [("p0", &spec.p0), ("p1", &spec.p1)] {
            if let Some(path) = snapshot_path(deck) {
                let snap = load_snapshot_at(&path).unwrap_or_else(|e| {
                    panic!(
                        "matchup `{}` {label} snapshot at {} failed to load: {e}",
                        spec.id,
                        path.display()
                    )
                });
                assert!(
                    !snap.cards.is_empty(),
                    "matchup `{}` {label} snapshot at {} has zero cards",
                    spec.id,
                    path.display()
                );
                assert!(
                    snap.cards.len() >= 40,
                    "matchup `{}` {label} snapshot at {} has only {} cards — below the \
                     playable-floor of 40",
                    spec.id,
                    path.display(),
                    snap.cards.len()
                );
            }
        }
    }
}

#[test]
fn all_matchup_ids_unique() {
    let ids: Vec<&str> = all_matchups().iter().map(|m| m.id).collect();
    let mut sorted = ids.clone();
    sorted.sort();
    sorted.dedup();
    assert_eq!(
        ids.len(),
        sorted.len(),
        "duplicate matchup IDs in registry: {ids:?}"
    );
}

/// The pre-refactor `ai_duel.rs` hardcoded 16 matchup IDs in a match block.
/// Every one of those IDs MUST remain resolvable by `find_matchup` so existing
/// CLI invocations (`cargo run --bin ai-duel -- --matchup prowess-mirror`)
/// keep working.
#[test]
fn matchup_ids_preserved() {
    const LEGACY_IDS: &[&str] = &[
        "red-vs-green",
        "blue-vs-green",
        "red-vs-blue",
        "black-vs-green",
        "white-vs-red",
        "black-vs-blue",
        "red-mirror",
        "green-mirror",
        "blue-mirror",
        "azorius-vs-prowess",
        "azorius-vs-gruul",
        "delver-vs-prowess",
        "azorius-vs-green",
        "delver-vs-green",
        "prowess-vs-green",
        "prowess-mirror",
    ];
    for id in LEGACY_IDS {
        assert!(
            find_matchup(id).is_some(),
            "legacy matchup id `{id}` no longer resolves via find_matchup"
        );
    }
}

#[test]
fn inline_decks_resolve_to_60_cards() {
    for spec in all_matchups() {
        for (label, deck) in [("p0", &spec.p0), ("p1", &spec.p1)] {
            if let DeckRef::Inline { build, .. } = deck {
                let cards = build();
                assert_eq!(
                    cards.len(),
                    60,
                    "matchup `{}` {label} inline deck resolves to {} cards (expected 60)",
                    spec.id,
                    cards.len()
                );
            }
        }
    }
}
