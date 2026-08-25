# Repository Audit

## Root Directory
| File/Folder | Classification | Action | Reason |
| --- | --- | --- | --- |
| `future.md` | MOVE | Move to `docs/hackathon.md` (or similar) | Project planning/future work belongs in docs. |
| `Problem_Faced.md` | MOVE | Move to `docs/` | Historical/diagnostic documentation. |
| `Project_Readme.md` | MOVE | Rename to `README.md` | Standardize naming. |
| `reproduce_v2.ps1` | MOVE | Move to `scripts/reproduce_v2.ps1` | Executable scripts belong in a scripts directory. |

## Backend Root (`backend/`)
| File/Folder | Classification | Action | Reason |
| --- | --- | --- | --- |
| `.env` | GITIGNORE | Delete from repo, add to `.gitignore` | Contains local secrets and config. |
| `.env.example` | MOVE | Move to root directory | Should be at the project root for easy setup. |
| `evaluation_report.md` | MOVE | Move to `docs/evaluation.md` | Key V2 evaluation documentation. |
| `evaluation_results_v2.json`| MOVE | Move to `data/v2/` or `docs/` | Useful V2 evaluation artifact. |
| `phase_d_report.md` | MOVE | Move to `docs/history/` | Historical report. |
| `recoverai.db` | GITIGNORE | Delete from repo, add to `.gitignore` | Local development SQLite database. |
| `test_idempotency.db` | GITIGNORE | Delete from repo, add to `.gitignore` | Local test database. |
| `scratch_trace.py` | DELETE | Delete | Temporary debug script. |

## Backend Scripts & Scratch
| File/Folder | Classification | Action | Reason |
| --- | --- | --- | --- |
| `backend/scratch/` | DELETE | Delete entirely | Temporary debug artifacts (`ml_diag.py`). |
| `backend/scripts/evaluate_batch.py` | DELETE | Delete | Obsolete V1 script. |
| `backend/scripts/evaluate_batch_v2.py`| MOVE | Move to `scripts/evaluate_batch.py` | Final V2 evaluation script. |

## Data Directory (`data/`)
| File/Folder | Classification | Action | Reason |
| --- | --- | --- | --- |
| `synthetic_dataset.csv`, etc. | DELETE | Delete | Obsolete V1 datasets. |
| `generate_synthetic_data.py` | DELETE | Delete | Obsolete V1 generator. |
| `v2/*` | KEEP | Keep in `data/v2/` | Final V2 dataset split. |
| `generate_synthetic_data_v2.py`| MOVE | Move to `scripts/generate_synthetic_data.py` | Final V2 generator. |

## Models Directory (`backend/app/models/`)
| File/Folder | Classification | Action | Reason |
| --- | --- | --- | --- |
| `recovery_model.pkl` | DELETE | Delete | Obsolete V1 model. |
| `model_config.json` | DELETE | Delete | Obsolete V1 config. |
| `train_ml_model.py` | DELETE | Delete | Obsolete V1 training script. |
| `recovery_model_v2.pkl` | MOVE | Move to `models/` | Final V2 model artifact. |
| `model_config_v2.json` | MOVE | Move to `models/` | Final V2 model config. |
| `feature_importance_v2.csv` | MOVE | Move to `models/` | Final V2 model features. |
| `train_v2_model.py` | MOVE | Move to `scripts/train_model.py` | Final V2 training script. |

## Notebooks
| File/Folder | Classification | Action | Reason |
| --- | --- | --- | --- |
| `notebooks/evaluation.ipynb` | DELETE | Delete | Temporary diagnostic notebook. |

## Caches and IDE Files
| File/Folder | Classification | Action | Reason |
| --- | --- | --- | --- |
| `__pycache__/`, `.pytest_cache/` | GITIGNORE | Delete from repo, add to `.gitignore` | Auto-generated python bytecodes. |

---

*Note: Frontend `node_modules`, `dist`, and Backend `.venv` are already omitted from this list but will be explicitly ignored in `.gitignore`.*
