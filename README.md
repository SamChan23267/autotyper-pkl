# autotyper-pkl

A [PKL](https://pkl-lang.org) configuration library that lets you tune every
aspect of human-like typing behaviour for an autotyper.  All six "human factor"
parameters are first-class, user-configurable properties with sane defaults and
built-in constraints.  Four ready-made presets are included so you can get
started immediately.

---

## Parameters

All timing values are in **milliseconds**.  Probability values are `Float`s in
the range `0.0` (never) to `1.0` (always).  Every mean timing property has a
companion `*StdDev` property; consumers should sample
`Normal(mean, stdDev)` and clamp to `0` when computing an actual delay.

| Property | Type | Default | Description |
|---|---|---|---|
| `wordPause` | `Int` | `80` | Mean pause between words. |
| `wordPauseStdDev` | `Int` | `20` | Std-dev for word pause (normal distribution). |
| `punctuationPause` | `Int` | `200` | Mean **extra** pause after `.` `,` `!` `?` `;` `:` `—`. |
| `punctuationPauseStdDev` | `Int` | `50` | Std-dev for punctuation pause. |
| `transpositionProbability` | `Float` | `0.05` | Probability per word that two adjacent characters are accidentally swapped and then corrected (e.g. `the` → `teh` → `the`). |
| `longerPauseProbability` | `Float` | `0.02` | Probability per word that a longer "distraction" pause occurs. |
| `longerPauseDuration` | `Int` | `1500` | Mean duration of the occasional longer pause. |
| `longerPauseDurationStdDev` | `Int` | `500` | Std-dev for the longer pause. |
| `capitalizationDelay` | `Int` | `30` | Mean extra delay before a capital letter (Shift-key hesitation). |
| `capitalizationDelayStdDev` | `Int` | `10` | Std-dev for capitalization delay. |
| `keystrokeDelay` | `Int` | `60` | Mean delay between consecutive keystrokes (typing speed). |
| `keystrokeDelayStdDev` | `Int` | `15` | Std-dev for keystroke delay (normal distribution of speed). |

---

## Presets

Four premade configurations are provided in the `presets/` directory.  Each
one amends `AutoTyper.pkl` with a consistent, self-describing set of values.

| Preset file | WPM (approx.) | Transposition rate | Description |
|---|---|---|---|
| `presets/FastTypist.pkl` | ~120–140 | ~3 % | Proficient touch-typist, rare errors. |
| `presets/Realistic.pkl` | ~75 | ~4 % | Everyday office worker at a comfortable pace. |
| `presets/CarefulTypist.pkl` | ~25–30 | ~1 % | Deliberate, accuracy-focused typist. |
| `presets/Beginner.pkl` | ~10–15 | ~15 % | Hunt-and-peck learner with frequent pauses. |

---

## Usage

### Use the defaults

```pkl
amends "AutoTyper.pkl"
// nothing to change — all defaults apply
```

### Start from a preset

```pkl
amends "presets/Realistic.pkl"

// override individual values as needed
wordPause = 120
transpositionProbability = 0.06
```

### Evaluate a configuration

```sh
pkl eval AutoTyper.pkl
pkl eval presets/Realistic.pkl
pkl eval presets/FastTypist.pkl
```

### Run the tests

```sh
pkl test tests/AutoTyperTest.pkl
```

---

## File structure

```
AutoTyper.pkl            ← main module with all parameters and defaults
presets/
  Realistic.pkl          ← everyday typist preset
  FastTypist.pkl         ← fast / proficient typist preset
  CarefulTypist.pkl      ← slow / careful typist preset
  Beginner.pkl           ← beginner / hunt-and-peck typist preset
tests/
  AutoTyperTest.pkl      ← PKL unit tests (run with `pkl test`)
```
