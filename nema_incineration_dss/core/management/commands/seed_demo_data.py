import io

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from core.models import UserProfile, Dataset
import numpy as np
import pandas as pd

COLUMNS = [
"record_time","aicsa_071","co_a","f051_sp_int","f052_sp_int","f081_sp_int","hcl_a","hf_a","jz_zl",
"nox_a","p062a_sp_int","p062b_sp_int","p071a_sp_int","p071b_sp_int","si02_a","so2_a","tia_051",
"tia_057","tia_075","ti_053","yyz_wf_t_rc","i052"
]

class Command(BaseCommand):
    help = "Create synthetic records for local software testing. These are NOT NEMA/plant measurements."

    def handle(self, *args, **kwargs):
        rng = np.random.default_rng(42)
        n = 300
        t = pd.date_range("2026-01-01", periods=n, freq="h")
        data = {"record_time": t}
        for c in COLUMNS[1:]:
            data[c] = rng.normal(100, 15, n)
        data["co_a"] = np.abs(rng.normal(15, 4, n))
        data["nox_a"] = np.abs(rng.normal(80, 20, n))
        data["so2_a"] = np.abs(rng.normal(30, 8, n))
        data["hcl_a"] = np.abs(rng.normal(8, 2, n))
        data["hf_a"] = np.abs(rng.normal(3, 1, n))
        df = pd.DataFrame(data)
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        u, created = User.objects.get_or_create(username="officer")
        if created:
            u.set_password("officer123")
            u.save()
        UserProfile.objects.get_or_create(
            user=u, defaults={"role": UserProfile.ROLE_OFFICER}
        )
        dataset = Dataset(
            name="demo_output.csv",
            uploaded_by=u, row_count=n, column_count=len(df.columns),
            columns=list(df.columns), preview=df.head(5).to_dict(orient="records")
        )
        dataset.file.save(
            "demo_output.csv",
            ContentFile(csv_buffer.getvalue().encode("utf-8")),
            save=True,
        )
        self.stdout.write(self.style.SUCCESS(
            "Synthetic demo dataset created. Login: officer / officer123"
        ))
