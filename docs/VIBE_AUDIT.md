# ChefChat Vibe Codebase Audit (vibe/)

## Samenvatting
- **Overall score:** Oranje – sterke modularisatie (modes, core, cli), maar enkele hoge-risico bevindingen: niet-afgedwongen command-allowlist, mogelijke crash in file indexer bij rootwissel, en wachters zonder logging/timeout.
- **Scope:** volledige `vibe/` subtree (cli, core, modes, setup/onboarding, utils). Build/venv/node_modules uitgesloten.
- **Methode:** statische code-inspectie, focus op architectuur, codekwaliteit, security en performance; geen dynamische tests uitgevoerd.

## 1. Structurele Analyse & Onderhoudbaarheid
| Aspect | Bevinding | Impact | Aanbeveling |
| --- | --- | --- | --- |
| Concurrency & state | Mutatie van `self._active_rebuilds` tijdens iteratie kan `RuntimeError: dictionary changed size during iteration` geven bij rootwissel @vibe/core/autocompletion/file_indexer/indexer.py:57-64 | Hoog | Itereer over kopie (`list(self._active_rebuilds.items())`) of verzamel keys eerst en `pop` daarna. Voeg lock-gedrag toe bij annuleren. |
| Rebuild-wachtroute | `_wait_for_rebuild` wacht onbeperkt; bij vastlopende rebuild blokkeert REPL/index retrieval @vibe/core/autocompletion/file_indexer/indexer.py:155-160 | Middel | Voeg timeout/backoff + log toe; forceer cancel na drempel en lever laatste snapshot terug. |
| Exception-handling watcher | Watch-loop slikt alle exceptions zonder logging @vibe/core/autocompletion/file_indexer/watcher.py:56-72 | Middel | Log exceptions en signaleer stop, zodat caller kan herstarten. |
| Modulariteit modes | Modes opgesplitst (types/constants/manager/security/executor/prompts/helpers) i.p.v. God class @vibe/modes/* | Laag/Positief | Behouden; documenteer extensiepunten (nieuwe mode, tool whitelist). |
| CLI entrypoint complexiteit | `main()` bevat veel setup/IO met brede try/except en herhaalde file-creatie @vibe/cli/entrypoint.py:158-220 | Laag | Factoriseer file-initialisatie naar helper; beperk catch-all excepts (alleen specifieke). |

## 2. Kwaliteits- & Stijlanalyse (Code Smells)
| Locatie | Probleem | Prioriteit | Oplossing |
| --- | --- | --- | --- |
| vibe/core/autocompletion/file_indexer/indexer.py:57-64 | Dict mutatie tijdens iteratie → potentieel crashpad | Hoog | Gebruik kopie of verzamel te annuleren entries in aparte lijst. |
| vibe/core/autocompletion/file_indexer/watcher.py:56-72 | Exceptions worden stil genegeerd → verborgen degradatie | Middel | `logger.exception` + stop/retry-mechanisme. |
| vibe/core/tools/executor.py:219-229 | Allowlist check heeft alleen `pass`; inconsistent met docstring “must go through executor” | Hoog | Raise `ToolError` bij onbekende executable; maak allowlist uitbreidbaar via config indien nodig. |
| vibe/cli/entrypoint.py:158-220 | Grote functie, meerdere nested try/except; PLR0912/0915 hints | Laag | Split per concern (config bootstrap, session-restore, mode dispatch). |
| Cross-cutting | Geen type-narrowing van env-injectie; dotenv laadt alle keys | Laag | Beperk tot prefix (bijv. `VIBE_`) of whitelist bekende env-keys. |

## 3. Beveiligingsanalyse
| Locatie/Module | Kwetsbaarheid | Ernst | Mitigatie |
| --- | --- | --- | --- |
| vibe/core/tools/executor.py:219-229 | Allowlist niet afgedwongen ⇒ elke executable kan draaien (command abuse) | Hoog | Hard block onbekende executables (`raise ToolError`); log poging; bied config-override met expliciete opt-in. |
| vibe/core/config.py:49-55 | .env wordt ongewijzigd in `os.environ` geladen; potentiële env-injectie in gedeelde omgevingen | Laag | Laad alleen bekende/prefixed keys; valideer en mask logs. |
| vibe/core/autocompletion/file_indexer/indexer.py:98-104 | `self._store.rebuild` in lock, maar bij uitzonderingen in watcher ontbreekt logging; kan verborgen integriteitsverlies geven | Middel | Log fouten en markeer index als “degraded”, trigger herbouw. |

## 4. Prestatieanalyse
| Locatie | Bottleneck | Impact | Aanbeveling |
| --- | --- | --- | --- |
| vibe/core/autocompletion/file_indexer/indexer.py:155-160 | Onbegrensde wait op rebuild → REPL kan hangen bij IO-stall | Middel | Timeout + cancel; eventueel niet-blockende snapshot teruggeven. |
| vibe/core/autocompletion/file_indexer/store.py:50-79 | Bij mass_change_threshold wordt sync rebuild gedaan in watcher-context; kan UI-pauze veroorzaken | Laag | Offload rebuild naar achtergrond executor; verhoog drempel of maak config-gedreven. |
| vibe/core/autocompletion/file_indexer/store.py:125-155 | Recursieve scandir zonder throttling; kan warm pad met veel kleine files vertragen | Laag | Overweeg batch-yield of parallel walk (config flags bestaan al) en honour `file_indexer_parallel_walk` default in config. |

## Quick Wins (hoogste ROI)
1) Enforce allowlist in `SecureCommandExecutor.execute` (2-3 regels) – sluit command abuse.  
2) Fix dict-mutatie bij rootwissel in file indexer.  
3) Voeg logging + timeout in watch/rebuild-pad voor zichtbaarheid en hang-preventie.  

## Aanbevolen Actieplan
- **Week 1:** Apply quick wins 1-3; schrijf regressietest voor file indexer root switch.  
- **Week 2:** Refactor `cli.entrypoint.main` in kleinere helpers; introduceer env-prefix filter.  
- **Week 3:** Config-opties documenteren (parallel walk, max workers) en defaults tunen op grote repositories.  

## Detailnotities
- Modesysteem is netjes gelaagd; security-patronen (WRITE_BASH_PATTERNS) zijn module-level compiled → goed voor performance.  
- File indexer gebruikt locks correct voor snapshot; risico zit vooral in rebuild-cancel-boekhouding.  
- REPL prompt handling en command routing zijn duidelijk; geen directe security issues gevonden.  
- Config validatie via Pydantic v2; `load_api_keys_from_env` laadt .env maar zonder whitelisting.  

## Risicoprioritering
- **Hoog:** Command allowlist niet enforced; crash bij rootwissel file indexer.  
- **Middel:** Watcher exceptions stil; onbegrensde rebuild-wacht; env-injectie via .env.  
- **Laag:** CLI complexiteit; sync mass-rebuild; scandir zonder throttling.  

---
Laat weten of je aanvullende secties (bv. testplan of exploit-scenario’s) wil; kan worden toegevoegd.
