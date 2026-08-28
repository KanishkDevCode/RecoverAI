$ErrorActionPreference = "Stop"

# Download PostgreSQL
Invoke-WebRequest -Uri "https://get.enterprisedb.com/postgresql/postgresql-15.3-1-windows-binaries.zip" -OutFile "postgres.zip"

# Extract
Expand-Archive -Path "postgres.zip" -DestinationPath "pgsql" -Force

# Initialize Database Cluster
$pgBin = "$pwd\pgsql\pgsql\bin"
& "$pgBin\initdb.exe" -U postgres -A trust -D "$pwd\pgsql\data"

# Start PostgreSQL server in the background
Start-Process -FilePath "$pgBin\pg_ctl.exe" -ArgumentList "start -D `"$pwd\pgsql\data`" -l `"$pwd\pgsql\logfile.log`"" -NoNewWindow

Start-Sleep -Seconds 3

# Create database
& "$pgBin\createdb.exe" -U postgres -h localhost test_recoverai_v2
