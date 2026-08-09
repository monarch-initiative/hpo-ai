# CHEBI Selection Guide for HPO Chemical Phenotypes

This guide provides rules for selecting the correct CHEBI (or PRO) entity
when multiple candidates exist. It is injected into the LLM enricher's
system prompt for disambiguation.

## General Principles

- Pick the CHEBI term representing **what is actually measured** in the
  clinical assay, not a broader category or role.
- Prefer specific chemical entities over role-based groupings (e.g.,
  "glucose" not "monosaccharide").
- If the entity is a protein or enzyme, use a **PRO** identifier instead
  of CHEBI.

## Elements and Ions

Per [upheno#946](https://github.com/obophenotype/upheno/issues/946), HPO
uses **atom forms** for elements while GO uses ions:

- **calcium** → CHEBI:22984 (calcium atom), NOT calcium(2+)
- **potassium** → CHEBI:26216 (potassium atom), NOT potassium(1+)
- **sodium** → CHEBI:26708 (sodium atom), NOT sodium(1+)
- **magnesium** → CHEBI:25107 (magnesium atom), NOT magnesium(2+)
- **iron** → CHEBI:18248 (iron atom), NOT iron(2+) or iron(3+)
- **copper** → CHEBI:28694 (copper atom), NOT copper(2+)
- **zinc** → CHEBI:27363 (zinc atom), NOT zinc(2+)

Exception: **chloride** → CHEBI:17996 (chloride), because what is
measured is the chloride anion, not elemental chlorine.

## Never Pick

- Salts (e.g., calcium chloride, sodium bicarbonate)
- Dietary or supplemental forms (e.g., calcium carbonate supplement)
- Metallic/elemental solid forms
- Role-based groupings (e.g., "antioxidant", "cofactor")
- Pharmacological classes

## Amino Acids

- Prefer the **L-form** unless the D-form is explicitly stated in the
  phenotype label.
- Use the parent amino acid, not a derivative (e.g., "leucine" not
  "L-leucine residue").

## Hormones and Enzymes

Many hormones and enzymes are proteins. Use these heuristics:

- If the entity ends in "-ase" (kinase, phosphatase, transferase, etc.),
  it is likely a protein → use **PRO**.
- If the entity is a peptide hormone with a CHEBI entry (e.g., insulin
  has both CHEBI and PRO), prefer **PRO** for HPO.
- Common protein abbreviations: CK, ALT, AST, ALP, GGT, PTH, AFP, CRP,
  IgA, IgG, IgM, IgE → all map to PRO identifiers.

## Lipoproteins

- LDL, HDL, VLDL are lipoprotein cholesterol complexes and have CHEBI
  entries (CHEBI:47774, CHEBI:47775, CHEBI:47773).
- Use the CHEBI lipoprotein cholesterol term, not a PRO term.

## Disambiguation When Multiple Candidates Exist

When OAK search returns multiple CHEBI candidates:

1. **Discard** any candidate that is a salt, role, or dietary form.
2. **Prefer** the candidate whose label most closely matches the query.
3. **Prefer** atom forms over ionic forms for elements.
4. **Prefer** the more specific term over a broader category.
5. If still ambiguous, pick the candidate with the shortest label (less
   qualified = more canonical).

## Output Format

When selecting a CHEBI entity, always provide:
- The CHEBI/PRO ID
- The canonical label
- A brief rationale explaining why this candidate was chosen
