import os
import glob
import re

TARGET_STRING = "    Base.metadata.drop_all(bind=engine)"
TARGET_STRING_2 = "        Base.metadata.drop_all(bind=engine)"

REPLACEMENT_TEMPLATE = """    # Safe cleanup using reversed sorted_tables to respect FKs
{indent}db = TestingSessionLocal()
{indent}try:
{indent}    for table in reversed(Base.metadata.sorted_tables):
{indent}        db.execute(table.delete())
{indent}    db.commit()
{indent}finally:
{indent}    db.close()"""

def patch_tests():
    files = glob.glob("tests/**/*.py", recursive=True)
    count = 0
    for file in files:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if "Base.metadata.drop_all" in content:
            new_lines = []
            for line in content.split("\n"):
                if "Base.metadata.drop_all(bind=engine)" in line:
                    indent = line.split("Base")[0]
                    replacement = REPLACEMENT_TEMPLATE.format(indent=indent)
                    new_lines.append(replacement)
                else:
                    new_lines.append(line)
            
            with open(file, 'w', encoding='utf-8') as f:
                f.write("\n".join(new_lines))
            count += 1
            print(f"Patched: {file}")
            
    print(f"Total patched: {count}")

if __name__ == "__main__":
    patch_tests()
