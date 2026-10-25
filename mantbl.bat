@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

REM ============================================================
REM  mantbl.bat - запуск IDE «Манты Edition» для Java-проекта
REM ============================================================
REM
REM  ТРЕБОВАНИЯ:
REM    * Python >= 3.12.7       https://www.python.org/downloads/
REM    * OpenJDK 25.x (строго)  https://adoptium.net/
REM      Эталон, на котором тестировалась IDE:
REM        openjdk version "25.0.4.1" 2026-08-18 LTS
REM      Любая другая мажорная версия JDK (17, 21, 26…)
REM      НЕ ПОДДЕРЖИВАЕТСЯ — отладчик jdtls настроен
REM      именно под JDK 25.
REM
REM  OPENROUTER_API_KEY:
REM    Для ИИ-оптимизации графа в .env (рядом с mantbl.bat)
REM    должен быть указан OPENROUTER_API_KEY.
REM    Если ключа нет — скрипт предложит его ввести
REM    (можно пропустить Enter-ом, но ИИ-оптимизация
REM    тогда работать не будет). Получить ключ:
REM      https://openrouter.ai/keys
REM
REM  Использование:
REM      mantbl.bat "C:\path\to\java\project"
REM  или просто:
REM      mantbl.bat
REM ============================================================

REM --- 1. Путь к проекту ---------------------------------------
set "PROJECT_PATH=%~1"
if "%PROJECT_PATH%"=="" (
    set "PROJECT_PATH=%~dp0"
    echo [i] Путь к проекту не указан. Использую папку скрипта:
    echo     "!PROJECT_PATH!"
)

call :normalize_path PROJECT_PATH

if not exist "%PROJECT_PATH%" (
    echo [X] Папка проекта не найдена: "%PROJECT_PATH%"
    exit /b 1
)

echo.
echo ============================================================
echo   IDE «Манты Edition»
echo   Проект: "%PROJECT_PATH%"
echo ============================================================
echo.

REM --- 2. Проверка Python --------------------------------------
echo [1/7] Проверка Python...
set "PY_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3"
) else (
    where python >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python"
)

if "%PY_CMD%"=="" goto :err_no_python

for /f "delims=" %%v in ('%PY_CMD% --version 2^>^&1') do (
    echo     Найден: %%v
)

REM Проверка версии: минимум 3.12.7
%PY_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3,12,7) else 1)"
if errorlevel 1 goto :err_python_too_old

REM --- 3. Проверка Java ----------------------------------------
echo [2/7] Проверка Java...
where java >nul 2>nul
if errorlevel 1 goto :err_no_java

where javac >nul 2>nul
if errorlevel 1 goto :err_no_javac

REM Извлекаем версию: строка вида
REM   openjdk version "25.0.4.1" 2026-08-18 LTS
REM → JAVA_VERSION = 25.0.4.1
set "JAVA_VERSION="
for /f tokens^=2^ delims^=^" %%v in ('java -version 2^>^&1 ^| findstr /i "version"') do (
    set "JAVA_VERSION=%%v"
)

if not defined JAVA_VERSION (
    echo [X] Не удалось определить версию Java.
    goto :err_java_unknown
)

echo     Найдена: !JAVA_VERSION!

REM Извлекаем мажорную версию: 25.0.4.1 → 25
set "JAVA_MAJOR="
for /f "tokens=1 delims=." %%m in ("!JAVA_VERSION!") do set "JAVA_MAJOR=%%m"

if not defined JAVA_MAJOR goto :err_java_unknown

REM Строго JDK 25
if !JAVA_MAJOR! NEQ 25 goto :err_java_not_25

REM --- 4. Проверка pip -----------------------------------------
echo [3/7] Проверка pip...
%PY_CMD% -m pip --version >nul 2>nul
if errorlevel 1 (
    echo [!] pip не найден. Пробую установить...
    %PY_CMD% -m ensurepip --upgrade >nul 2>nul
    if errorlevel 1 goto :err_no_pip
)
for /f "delims=" %%v in ('%PY_CMD% -m pip --version 2^>^&1') do (
    echo     Найден: %%v
)

REM --- 5. Проверка наличия основного скрипта -------------------
echo [4/7] Проверка файлов IDE...
set "IDE_SCRIPT=%~dp0import os.txt"
if not exist "%IDE_SCRIPT%" (
    if exist "%~dp0main.py" (
        set "IDE_SCRIPT=%~dp0main.py"
    ) else (
        if exist "%~dp0test_main.py" (
            set "IDE_SCRIPT=%~dp0test_main.py"
        ) else (
            goto :err_no_script
        )
    )
)
echo     Основной скрипт: "!IDE_SCRIPT!"

REM --- 6. Проверка папки tools / установка через setup_tools.py -
echo [5/7] Проверка папки tools...
set "TOOLS_DIR=%~dp0tools"
set "SETUP_TOOLS=%~dp0setup_tools.py"

if exist "%TOOLS_DIR%\" (
    echo     Папка tools уже есть.
    goto :tools_ready
)

echo     Папка tools не найдена. Запускаю setup_tools.py...
if not exist "%SETUP_TOOLS%" (
    echo [X] Не найден setup_tools.py: "%SETUP_TOOLS%"
    echo     Создайте файл setup_tools.py или папку tools вручную.
    exit /b 1
)

%PY_CMD% "%SETUP_TOOLS%"
if errorlevel 1 (
    echo [X] setup_tools.py завершился с ошибкой.
    exit /b 1
)

if not exist "%TOOLS_DIR%\" (
    echo [X] setup_tools.py завершился, но папка tools не появилась.
    echo     Проверьте вывод setup_tools.py выше.
    exit /b 1
)
echo     Папка tools успешно создана.

:tools_ready

REM --- 7. Проверка и установка Python-зависимостей -------------
echo [6/7] Проверка Python-зависимостей...

set "REQ_FILE=%~dp0requirements.txt"
set "INSTALL_NEEDED=0"

%PY_CMD% -c "import webui" >nul 2>nul
if errorlevel 1 set "INSTALL_NEEDED=1"

%PY_CMD% -c "import fastapi" >nul 2>nul
if errorlevel 1 set "INSTALL_NEEDED=1"

%PY_CMD% -c "import uvicorn" >nul 2>nul
if errorlevel 1 set "INSTALL_NEEDED=1"

if "%INSTALL_NEEDED%"=="1" goto :do_install_deps
echo     Все ключевые зависимости уже установлены.
goto :deps_ready

:do_install_deps
echo     Некоторые зависимости отсутствуют. Устанавливаю...
if not exist "%REQ_FILE%" goto :install_manual
echo     Использую "%REQ_FILE%"
%PY_CMD% -m pip install -r "%REQ_FILE%"
if errorlevel 1 goto :err_pip_fail
goto :deps_ready

:install_manual
echo     requirements.txt не найден. Устанавливаю пакеты вручную...
%PY_CMD% -m pip install webui fastapi "uvicorn[standard]" python-multipart
if errorlevel 1 goto :err_pip_fail

:deps_ready

REM --- 8. .env и OPENROUTER_API_KEY ----------------------------
echo [7/7] Проверка .env и OPENROUTER_API_KEY...

set "ENV_FILE=%~dp0.env"
if not exist "%ENV_FILE%" (
    echo     .env не найден. Создаю пустой файл: "!ENV_FILE!"
    type nul > "%ENV_FILE%"
)

REM Проверяем, есть ли уже OPENROUTER_API_KEY с непустым значением
%PY_CMD% -c "import sys,pathlib; p=pathlib.Path(r'%ENV_FILE%'); lines=(p.read_text(encoding='utf-8',errors='ignore').splitlines() if p.exists() else []); ok=any('=' in l and l.split('=',1)[0].strip()=='OPENROUTER_API_KEY' and l.split('=',1)[1].strip() for l in lines); sys.exit(0 if ok else 1)"
if not errorlevel 1 (
    echo     OPENROUTER_API_KEY уже указан в .env
    goto :env_ready
)

REM Ключа нет. Берём из окружения или спрашиваем.
if not "%OPENROUTER_API_KEY%"=="" (
    echo     Использую OPENROUTER_API_KEY из переменной окружения.
    set "USER_KEY=!OPENROUTER_API_KEY!"
) else (
    echo.
    echo     OPENROUTER_API_KEY не найден ни в .env, ни в окружении.
    echo     Получить ключ можно на https://openrouter.ai/keys
    echo.
    set /p "USER_KEY=    Введите OPENROUTER_API_KEY (Enter - пропустить): "
)

if "!USER_KEY!"=="" (
    echo     [!] Ключ не задан. ИИ-оптимизация графа работать не будет.
    goto :env_ready
)

REM Удаляем старую строку OPENROUTER_API_KEY=... и дописываем актуальную
findstr /v /b /c:"OPENROUTER_API_KEY=" "%ENV_FILE%" > "%ENV_FILE%.tmp" 2>nul
>> "%ENV_FILE%.tmp" echo OPENROUTER_API_KEY=!USER_KEY!
move /y "%ENV_FILE%.tmp" "%ENV_FILE%" >nul 2>nul
if errorlevel 1 (
    echo [!] Не удалось обновить .env. Сохраните ключ вручную:
    echo     OPENROUTER_API_KEY=!USER_KEY!
    goto :env_ready
)
echo     OPENROUTER_API_KEY сохранён в .env

:env_ready

REM --- 9. WORKSPACE --------------------------------------------
set "WORKSPACE=%PROJECT_PATH%"
echo.
echo [i] WORKSPACE = "%WORKSPACE%"
echo.

REM --- 10. Запуск IDE ------------------------------------------
echo [i] Запуск IDE...
echo ------------------------------------------------------------
%PY_CMD% "%IDE_SCRIPT%"
set "EXIT_CODE=%ERRORLEVEL%"
echo ------------------------------------------------------------

if "%EXIT_CODE%"=="0" goto :ok_exit
echo [X] IDE завершилась с кодом %EXIT_CODE%.
endlocal & exit /b %EXIT_CODE%

:ok_exit
echo [OK] IDE завершилась штатно.
endlocal & exit /b 0


REM ============================================================
REM  Обработчики ошибок
REM ============================================================
:err_no_python
echo [X] Python не найден в PATH.
echo     Требуется Python >= 3.12.7.
echo     Установите с https://www.python.org/downloads/
echo     и включите опцию "Add Python to PATH" при установке.
exit /b 1

:err_python_too_old
echo [X] Версия Python слишком старая.
echo     Требуется Python >= 3.12.7.
echo     Обновите с https://www.python.org/downloads/
exit /b 1

:err_no_java
echo [X] Java не найдена в PATH.
echo     Требуется строго OpenJDK 25.x (эталон 25.0.4.1 LTS).
echo     Скачать: https://adoptium.net/
exit /b 1

:err_no_javac
echo [!] java найдена, но javac нет. Возможно, установлен только JRE.
echo     Для компиляции и отладки нужен JDK (с javac).
echo     Установите OpenJDK 25.x: https://adoptium.net/
exit /b 1

:err_java_unknown
echo [X] Не удалось определить версию Java.
echo     Требуется строго OpenJDK 25.x (эталон 25.0.4.1 LTS).
echo     Скачать: https://adoptium.net/
exit /b 1

:err_java_not_25
echo [X] Неподходящая версия Java: !JAVA_VERSION!
echo     Требуется строго OpenJDK 25.x (эталон 25.0.4.1 LTS).
echo     Скачать: https://adoptium.net/
exit /b 1

:err_no_pip
echo [X] Не удалось установить pip.
echo     Установите вручную: python -m ensurepip --upgrade
exit /b 1

:err_no_script
echo [X] Не найден основной скрипт IDE.
echo     Ожидался один из файлов рядом с mantbl.bat:
echo       - "import os.txt"
echo       - "main.py"
echo       - "test_main.py"
exit /b 1

:err_pip_fail
echo [X] Не удалось установить Python-зависимости.
exit /b 1


REM ============================================================
REM  Subroutine: normalize_path
REM  Убирает trailing '\', если это не корень диска (C:\).
REM ============================================================
:normalize_path
setlocal EnableDelayedExpansion
set "VAR_NAME=%~1"
call set "P=%%%VAR_NAME%%%"
if not defined P goto :np_done

set "LAST2=!P:~-2!"
set "LAST1=!P:~-1!"

if "!LAST1!"=="\" (
    if "!LAST2!"==":\" goto :np_apply
    set "P=!P:~0,-1!"
)

:np_apply
endlocal & set "%VAR_NAME%=%P%"
goto :eof

:np_done
endlocal
goto :eof