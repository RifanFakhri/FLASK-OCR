from database import SessionLocal
from sqlalchemy import text
import json

def save_parsing_result(result: dict):
    db = SessionLocal()

    try:
        metadata = result.get("metadata", {})

        sql = text("""
            INSERT INTO public.parsing_results (
                nosert,
                noreg,
                nmkpl,
                jenis_sert,
                jenis_survey,
                divisi,
                lokasi_survey,
                mem01,
                tgl_sert,
                tgl_berlaku,
                tgl_survey1,
                tgl_survey2,
                raw_result,
                created_at,
                updated_at
            ) VALUES (
                :nosert,
                :noreg,
                :nmkpl,
                :jenis_sert,
                :jenis_survey,
                :divisi,
                :lokasi_survey,
                :mem01,
                :tgl_sert,
                :tgl_berlaku,
                :tgl_survey1,
                :tgl_survey2,
                :raw_result,
                NOW(),
                NOW()
            )
        """)

        db.execute(sql, {
            "nosert": metadata.get("nosert"),
            "noreg": metadata.get("noreg"),
            "nmkpl": metadata.get("nmkpl"),
            "jenis_sert": metadata.get("jenis_sert"),
            "jenis_survey": metadata.get("jenis_survey"),
            "divisi": metadata.get("divisi"),
            "lokasi_survey": metadata.get("lokasi_survey"),
            "mem01": metadata.get("mem01"),
            "tgl_sert": metadata.get("tgl_sert"),
            "tgl_berlaku": metadata.get("tgl_berlaku"),
            "tgl_survey1": metadata.get("tgl_survey1"),
            "tgl_survey2": metadata.get("tgl_survey2"),
            "raw_result": json.dumps(result, ensure_ascii=False)
        })

        db.commit()

    except Exception as e:
        db.rollback()
        raise RuntimeError(f"DB insert failed: {e}")

    finally:
        db.close()
