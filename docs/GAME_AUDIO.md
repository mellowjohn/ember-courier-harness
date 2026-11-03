# Game audio

Ember provides an original, offline Web Audio mixer for browser games. Ask chat
to add game sound effects, music or ambience; the shared player is bundled in
the exact build proposal before review. It travels with previews, saved versions,
restores and exported ZIPs. No provider call, account or new dependency is needed
for synthesized audio. This does not import recordings or generate studio music.

Run `py -3.12 tools/audio_check.py --demo-only` to create a standalone **Sound
garden** HTML demo under ignored `.harness/audio-checks/`. Open its printed
`sound-garden.html` path and choose **Start sound demo**. The cue buttons and
keyboard actions demonstrate gameplay feedback; mix three music themes with
wind or ember ambience. Music and ambience are synthesized loops.

## Using sound in a game

The host supplies `ember-audio.js` when HTML or JavaScript uses `EmberAudio`.
Do not return or edit that protected file. It is inserted before game scripts;
existing approved runtime bytes are retained across ordinary revisions. It uses
one project file within the existing eight-file limit.

```javascript
const audio = EmberAudio.create();
audio.mountControls(document.querySelector('#sound-controls'));

startButton.addEventListener('click', async () => {
  await audio.unlock(); // Browser gesture required. Gameplay can continue if false.
  audio.startMusic('courier');
  audio.startAmbience('wind');
  startGame();
});

function collectParcel() {
  score += 1;
  audio.play('pickup'); // Once on collection, not once per animation frame.
}

function finishGame(won) {
  audio.stopAll();
  audio.play(won ? 'win' : 'lose');
}

pauseButton.addEventListener('click', () => audio.setPaused(true));
resumeButton.addEventListener('click', () => audio.setPaused(false));
addEventListener('pagehide', () => audio.dispose(), {once:true});
```

The nine cues are `jump`, `land`, `pickup`, `hit`, `attack`, `footstep`, `win`,
`lose` and `ui`. Effects accept `{pan:-1..1}` for stereo position. Repeated
triggers have a short cooldown, and each mixer caps its voices at 32. Use actual
movement, collision, interaction and terminal-state events as the triggers.

Music themes: `courier`, `explore`, `tension`. Custom music accepts
`{bpm:100,steps:[[60,64,67],null,[67],null]}`: 40–240 BPM, up to 64 eighth-note
steps, one to three integer MIDI pitches (24–96) per chord, `null` for a rest.
`tone({frequency:440,endFrequency:220,duration:.2,type:'sine',gain:.2,pan:0})`
provides custom effects; durations range from .02 to 4 seconds.

`setVolume(bus, 0..1)` controls `master`, `sfx`, `music` and `ambience` separately.
`setMuted(boolean)` retains the volume settings. `setPaused(boolean)` pauses
the audio clock; hidden documents also suspend it. `stopMusic()`,
`stopAmbience()` and `stopAll()` release loops, notes and timers; `dispose()`
also removes visibility handling and closes the context. Repeated music or
ambience starts replace the previous loop. A lookahead music scheduler skips
elapsed notes after timer throttling rather than replaying a backlog.

`mountControls(element)` creates labeled keyboard-accessible volume sliders,
enable and mute buttons, plus sound status. It returns a function that removes
the controls. The game should expose those controls or equivalent controls.
Settings are per mixer, without storage requirements in isolated previews.
`diagnostics()` reports context state, levels, loop selection and active voices;
it describes runtime state, not proof that a human heard the speakers.

Sound remains off until `unlock()` runs in a player gesture. Calls made before
unlock, while paused, after disposal or without browser audio support return
`false` and are not queued for later playback. Invalid parameters throw an error.
Keep gameplay independent of audio availability. After a browser interrupts
audio, use **Enable sound** to resume if automatic resume is blocked.

Task workers can add audio as part of their approved game task. Existing audio
is retained during polish; the polish workflow retains its approved file list.
All ordinary exact build and task acceptance rules still apply.

## Verification

`py -3.12 tools/offline_tests.py --pattern test_game_audio.py` checks no
autoplay, lifecycle, polyphony, cooldowns, invalid input, review boundaries,
retained runtime, restore and ZIP content using synthetic owner decisions.

`py -3.12 tools/audio_check.py` additionally uses the existing optional
[Chromium tooling](CHAT_BUILDS.md#browser-smoke-checks) to check actual Web Audio
signals and desktop/mobile controls. It creates screenshots, measured RMS
levels, a nine-cue WAV audition and a standalone demo. It makes no model call.
Browser signal checks verify sound generation and silence controls; listening
is still useful for judging the musical fit and mix of a particular game.
