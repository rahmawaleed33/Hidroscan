# Setup guide (no programming needed; copy and paste)

## A. One-time: install (10 minutes)
1. Install **Python 3.10+** from python.org (tick "Add Python to PATH" on Windows).
2. Unzip `hydroscan_rotate.zip`. Open a terminal **inside** the `hydroscan_rotate` folder.
3. Run: `pip install -r requirements.txt`

## B. Test the two sources that need no account (2 minutes)
Run: `python -m tools.live_check`
You get `LIVE_CHECK_EVIDENCE.md`. Expected: NASA POWER and SoilGrids = PASS with record counts and dates; the three GEE lines = SKIPPED.
If something says **FAIL**, send me the file. The URL pattern for SoilGrids WCS was written from documentation and has never been run against the real server, so a first-time FAIL there is plausible and fixable.

## C. Google Earth Engine (for Sentinel-2 history, rainfall, SMAP) (15 minutes, once)
1. Sign in with a Google account at **earthengine.google.com** and register for Earth Engine (choose non-commercial if it applies to you).
2. In **console.cloud.google.com** create a project (any name) and note its **Project ID**. Enable the Earth Engine API for it when asked.
3. In the terminal run: `earthengine authenticate` and follow the browser steps.
4. Tell the tool your project (replace MY-PROJECT):
   - Windows: `setx HYDROSCAN_GEE_PROJECT MY-PROJECT` then open a **new** terminal
   - Mac/Linux: `export HYDROSCAN_GEE_PROJECT=MY-PROJECT`
5. Run `python -m tools.live_check` again. All lines should now be attempted. The first GEE run can take several minutes (60 months × 3 sources); results are cached after that.

## D. Run the app
`streamlit run app.py` (turn on **Judge / Expert mode** in the sidebar to see sources, dates, resolutions).
WhatsApp simulation without any account: `python -m bot.simulate --demo`.

## E. If a source is down
The tool shows it as "unavailable" with the reason. It never fills the gap with sample data. Cached copies from an earlier successful run are used and labelled with their original retrieval date.
