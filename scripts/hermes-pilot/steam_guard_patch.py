"""Teach the pinned Hermes vault classifier the unlabeled Steam Guard widget."""
from hashlib import sha256
from pathlib import Path

CLASSIFIER = Path("/opt/hermes/agent/vault_login_classifier.py")
EXPECTED = "0166ac428b7d0926feee75f82dda688f82b19ca89c8444cfd6e8015b8b31eb97"

STEAM_GUARD_DETECTION = r'''
  // Steamworks uses an unlabeled group of five 1-character inputs for email 2FA.
  // Match only the official origin and the visible challenge text around the group.
  const steamGuard = new Set();
  const steamPartners = ["https://partner.steamgames.com", "https://partner.steampowered.com"];
  if (steamPartners.includes(window.location.origin)) {
    for (const section of document.querySelectorAll("section")) {
      const challenge = section.parentElement?.innerText || "";
      if (!/enter the code/i.test(challenge) || !/code from|sent to/i.test(challenge)) continue;
      const boxes = Array.from(section.querySelectorAll("input"))
        .filter(e => !e.disabled && !e.readOnly && e.getClientRects().length &&
          getComputedStyle(e).visibility === "visible");
      if (boxes.length !== 5 || !boxes[0].parentElement) continue;
      if (!boxes.every(e => e.type === "text" && e.maxLength === 1 &&
          e.parentElement === boxes[0].parentElement && e.form === boxes[0].form)) continue;
      const first = elements.indexOf(boxes[0]);
      if (!boxes.every((e, offset) => elements[first + offset] === e)) continue;
      boxes.forEach(e => steamGuard.add(e));
    }
    if (steamGuard.size !== 5) steamGuard.clear();
  }
'''

def patch_classifier(path=CLASSIFIER):
    source = path.read_bytes()
    if sha256(source).hexdigest() != EXPECTED:
        raise ValueError("Steam Guard patch requires the reviewed Hermes classifier")
    text = source.decode("utf-8")
    inspection = "  const out = elements.flatMap((element, index) => {"
    metadata = '      autocomplete: element.autocomplete || "",'
    if text.count(inspection) != 1 or text.count(metadata) != 1:
        raise ValueError("Hermes classifier patch anchors changed")
    text = text.replace(inspection, STEAM_GUARD_DETECTION + inspection)
    text = text.replace(metadata,
        '      autocomplete: steamGuard.has(element) ? "one-time-code steam-guard" : (element.autocomplete || ""),')
    selection = "    best = max(otp_controls, key=lambda c: c.score)"
    if text.count(selection) != 1:
        raise ValueError("Hermes OTP fill anchor changed")
    text = text.replace(selection, """    steam_boxes = [item for item in otp_controls if "steam-guard" in item.control.autocomplete.split()]
    if steam_boxes and (len(steam_boxes) != 5 or not re.fullmatch(r"[A-Za-z0-9]{5}", code)):
        return []
""" + selection)
    compile(text, str(path), "exec")
    path.write_text(text, encoding="utf-8")

if __name__ == "__main__":
    patch_classifier()
