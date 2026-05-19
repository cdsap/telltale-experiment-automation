import os
import shutil
import subprocess
from pathlib import Path


class Generator:
    def __init__(self, project_generator_path: str | os.PathLike[str]):
        self.project_generator_path = str(project_generator_path)

    def generate_project(self, output_dir: str | os.PathLike[str], options: dict[str, object]) -> Path:
        binary = shutil.which(self.project_generator_path) or self.project_generator_path
        if not Path(binary).exists() and shutil.which(binary) is None:
            raise FileNotFoundError(f"ProjectGenerator executable not found: {self.project_generator_path}")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        cmd = [binary, "generate-project", "--output-dir", str(output_path)]
        for key, value in options.items():
            if value is None or value is False:
                continue
            flag = "--" + key.replace("_", "-")
            if value is True:
                cmd.append(flag)
            else:
                cmd.extend([flag, str(value)])

        subprocess.run(cmd, check=True, text=True, capture_output=True)
        return output_path
