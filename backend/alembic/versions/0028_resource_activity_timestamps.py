"""Backfill resource activity timestamps."""

import sqlalchemy as sa
from alembic import op

revision = "0028_resource_activity_timestamps"
down_revision = "0027_official_model_project"
branch_labels = None
depends_on = None


def _advance(sql: str) -> None:
    op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    _advance(
        """
        UPDATE hyperparameter_templates
        SET updated_at = MAX(updated_at, COALESCE(deleted_at, updated_at))
        """
    )
    _advance(
        """
        UPDATE training_tasks AS t
        SET updated_at = (
          SELECT MAX(stamp) FROM (
            SELECT t.updated_at AS stamp
            UNION ALL
            SELECT MAX(COALESCE(m.deleted_at, m.finished_at, m.started_at,
                                m.updated_at, m.created_at))
            FROM training_models m WHERE m.training_task_id = t.id
            UNION ALL
            SELECT MAX(COALESCE(r.finished_at, r.started_at, r.enqueued_at))
            FROM training_runs r
            JOIN training_models m ON m.id = r.training_model_id
            WHERE m.training_task_id = t.id
            UNION ALL
            SELECT MAX(COALESCE(p.finished_at, p.started_at, p.created_at))
            FROM training_preparations p WHERE p.training_task_id = t.id
          )
        )
        """
    )
    _advance(
        """
        UPDATE projects AS p
        SET updated_at = (
          SELECT MAX(stamp) FROM (
            SELECT p.updated_at AS stamp
            UNION ALL
            SELECT MAX(m.created_at) FROM project_memberships m
            WHERE m.project_id = p.id
            UNION ALL
            SELECT MAX(l.updated_at) FROM labels l WHERE l.project_id = p.id
            UNION ALL
            SELECT MAX(v.updated_at) FROM videos v WHERE v.project_id = p.id
            UNION ALL
            SELECT MAX(s.updated_at) FROM sampling_plans s
            JOIN videos v ON v.id = s.video_id WHERE v.project_id = p.id
            UNION ALL
            SELECT MAX(f.created_at) FROM frames f
            JOIN videos v ON v.id = f.video_id WHERE v.project_id = p.id
            UNION ALL
            SELECT MAX(a.created_at) FROM annotations a
            JOIN frames f ON f.id = a.frame_id
            JOIN videos v ON v.id = f.video_id WHERE v.project_id = p.id
            UNION ALL
            SELECT MAX(t.updated_at) FROM tasks t WHERE t.project_id = p.id
            UNION ALL
            SELECT MAX(COALESCE(e.deleted_at, e.completed_at, e.started_at, e.created_at))
            FROM dataset_exports e WHERE e.project_id = p.id
          )
        )
        """
    )
    _advance(
        """
        UPDATE model_projects AS p
        SET updated_at = (
          SELECT MAX(stamp) FROM (
            SELECT p.updated_at AS stamp
            UNION ALL
            SELECT MAX(m.created_at) FROM model_project_memberships m
            WHERE m.model_project_id = p.id
            UNION ALL
            SELECT MAX(COALESCE(m.deleted_at, m.updated_at)) FROM inference_models m
            WHERE m.model_project_id = p.id
            UNION ALL
            SELECT MAX(a.updated_at) FROM model_artifacts a
            JOIN inference_models m ON m.id = a.model_id
            WHERE m.model_project_id = p.id
            UNION ALL
            SELECT MAX(COALESCE(d.deleted_at, d.completed_at, d.created_at))
            FROM evaluation_datasets d WHERE d.model_project_id = p.id
            UNION ALL
            SELECT MAX(COALESCE(e.finished_at, e.started_at, e.created_at))
            FROM model_evaluations e WHERE e.model_project_id = p.id
            UNION ALL
            SELECT MAX(COALESCE(r.deleted_at, r.saved_at))
            FROM model_inference_runs r
            JOIN inference_models m ON m.id = r.model_id
            WHERE m.model_project_id = p.id AND r.saved_at IS NOT NULL
            UNION ALL
            SELECT MAX(COALESCE(h.deleted_at, h.updated_at))
            FROM hyperparameter_templates h WHERE h.model_project_id = p.id
            UNION ALL
            SELECT MAX(t.updated_at) FROM tasks t
            WHERE t.model_project_id = p.id AND t.type <> 'infer_video'
            UNION ALL
            SELECT MAX(tt.updated_at) FROM training_tasks tt
            WHERE tt.id = p.training_task_id
          )
        )
        """
    )


def downgrade() -> None:
    # Historical timestamps cannot be reconstructed after they have been advanced.
    pass
