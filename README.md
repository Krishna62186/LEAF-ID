# Leaf Identifier

Leaf Identifier is a Flask web app that recognizes plants from leaf photos and shows a useful botanical profile.

## Features

- **Identify a leaf:** Choose or drag in a photo, take one with the live camera, or try the included demo leaf. Images up to 8 MB are supported.
- **Check the match:** See the likely species, common and scientific names, plant family, match confidence, and a reference image. The app also shows up to three other possible matches.
- **Explore plant information:** View a short overview, medicinal and culinary uses, household uses, growing advice, safety cautions, and a geographic habitat map.
- **Compare and inspect:** Compare your photo with a reference image and zoom in to view leaf details.
- **Use helpful tools:** Filter information by category, listen to the plant name, and print or share a short report.
- **Review recent scans:** Reopen up to six recent results saved in your browser, or clear the history.
- **Personalize the page:** Choose Forest, Ocean, Marigold, or Orchid colors. The interface offers English, Hindi, Tamil, and Telugu options.
- **Optional visual matches:** Add SerpApi and imgbb keys to show Google Lens matches. The uploaded image is temporarily hosted by imgbb for this lookup.
- **Reject weak matches:** Images that are not recognized as leaves, or whose match score is below the configured threshold, are rejected.

Plant identification is provided by Pl@ntNet. Plant details come from Wikipedia when available, with built-in botanical information used as a fallback. Some displayed text may not be available in every language.

## Requirements

- Python
- A Pl@ntNet API key from [my.plantnet.org](https://my.plantnet.org)

## Setup and run

Open a terminal in the project folder and install the dependencies:

```bash
python -m pip install -r requirements.txt
```

Create a `.env` file from `.env.example`, then add your Pl@ntNet key:

```env
PLANTNET_API_KEY=your_plantnet_api_key
```

Start the app:

```bash
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser. Allow camera access if you want to use Live Camera.

### Optional Google Lens matches

To enable Lens matches, also set both `SERPAPI_API_KEY` and `IMGBB_API_KEY` in `.env`. Leave them blank to use the app without this feature.

## Settings

- `MIN_SCORE` sets the minimum Pl@ntNet confidence required to accept a result. It defaults to `0.20` (20%). Increase it to be stricter or decrease it if valid leaves are often rejected.
- `MAX_UPLOAD_MB` is currently fixed at 8 MB.

## Notes

- An internet connection and a valid Pl@ntNet API key are needed for identification.
- Pl@ntNet may sometimes match flowers, whole plants, or other plant parts; photo-based identification is not perfect.
- Plant uses, care tips, and safety details are informational, not medical or food-safety advice. Never eat or use a wild plant based only on an app result.
