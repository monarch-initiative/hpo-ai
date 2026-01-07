
You are an architect and developer of AI-powered ontology curation systems. Your specific task is to develop a strategy to harmonise the representation of laboratory (aka chemical) phenotypes in the Human Phenotype Ontology. Below I copied a number of notes that you should read to get a sense of our initial thoughts. We are currently running the pipeline with human curators but I feel much of it should be automatable. As a first pass, please develop a strategy to implement an efficient system that:

0. Set up a project with monarch copier template
1. Automates the entire process
2. Uses evidence packets for collecting evidence for HP -> chemical entity curation from CHEBI and PRO
3. Allows us to proceed in chunks (branches)
4. Clearly identifies cases that need human input
5. For similar design see ~/ws/mondo-ai

For generating a final strategy document please:

- Read this whole task document which contains random notes about the process
- read this first successful PR we made: https://github.com/obophenotype/human-phenotype-ontology/pull/11380
- read this PR that contains the logic of the automated part of the pipeline: https://github.com/obophenotype/human-phenotype-ontology/pull/10560
- read these issues:https://github.com/obophenotype/upheno/issues/946; Naming conventions: https://github.com/obophenotype/human-phenotype-ontology/issues/11342
- look at @curated_phenotypes.tsv, and in particular some of the cases that were curated as part of PR 10560 above to get a sense what the reviewer is doing;

Strategy for dealing with chemical phenotypes


“Concentration/level/amount/circulating phenotypes” are abnormalities in levels of some chemical, usually with respect to some reference location like “blood” or “urine”. An example is “Abnormally increased circulating levels of lysine in the blood”. As there are thousands of clinically relevant concentration phenotypes, we are developing a method to ensure their consistent representation and classification in the Human Phenotype Ontology using Design Patterns.

Important links



GOALS
Develop a method to represent future “concentration phenotypes” in a consistent manner
Develop a method to retroactively harmonise the labels, definitions and logical axiomatisation of existing “concentration phenotypes”
Method to curate “concentration/level phenotypes” consistently moving forward
This is easily done with a DOSDP template, so omitting this for now. Requires a small additional step in the HPO2ROBOT, which is finding a suitable CHEBI or PRO id.

Method to retroactively harmonise “concentration phenotypes”

Select all existing “concentration phenotypes” using SPARQL

Assign all concentration phenotypes to patterns:
http://purl.obolibrary.org/obo/upheno/patterns-dev/abnormalConcentrationOfChemicalEntity.yaml
http://purl.obolibrary.org/obo/upheno/patterns-dev/abnormalConcentrationOfChemicalEntityInLocation.yaml
http://purl.obolibrary.org/obo/upheno/patterns/abnormalLevelOfChemicalEntity.yaml
http://purl.obolibrary.org/obo/upheno/patterns/abnormalLevelOfChemicalEntityInLocation.yaml

Absence of chemical entity
How to classify absence and decreased amount

Be mindful of differences between “total amount” and relative amounts.
Determine the “chemical” / “protein” for each of these using OntoGPT.
Run DOSDP generate to create harmonised labels and standaridsed definitions as specified by the patterns. For example “Abnormal blood inorganic cation concentration” becomes “Abnormal circulating inorganic cation concentration”.
Run the reasoner to determining missing and faulty subclass axioms among “concentration” and “level” phenotypes
Create a table which shows the changes in labels and definitions
Manually curate the changes above
Use ROBOT template to generate the axioms and merge them into the ontology

Exploration
Selecting concentration phenotypes
Used this SPARQL query to select potentially relevant phenotypes from Ubergraph.
Examples:
concentration_phenotype
label
http://purl.obolibrary.org/obo/HP_0003111
Abnormal blood ion concentration
http://purl.obolibrary.org/obo/HP_0004921
Abnormal magnesium concentration
http://purl.obolibrary.org/obo/HP_0004363
Abnormal circulating calcium concentration
http://purl.obolibrary.org/obo/HP_0040130
Abnormal serum iron concentration
http://purl.obolibrary.org/obo/HP_0100529
Abnormal blood phosphate concentration
http://purl.obolibrary.org/obo/HP_0011042
Abnormal blood potassium concentration
http://purl.obolibrary.org/obo/HP_0010931
Abnormal blood sodium concentration
http://purl.obolibrary.org/obo/HP_0008277
Abnormal blood zinc concentration
http://purl.obolibrary.org/obo/HP_0011422
Abnormal blood chloride concentration
http://purl.obolibrary.org/obo/HP_0010836
Abnormal circulating copper concentration
http://purl.obolibrary.org/obo/HP_0010927
Abnormal blood inorganic cation concentration


Task description Adam
Workbook: HPO Chemical Phenotypes
In the workbook, you only edit two sheets:


Notes

Concentration is not correct for urine: depends on the “concentration” of the Urine itself.
For Urine it is “level” - there is now a standard definition (reach out to peter)
Then you have terms for “enzymes” - sometimes they are measured by “activity” and concentration (in blood) of chemical. 
its fine to link them to the chemical entities rather than the biological processes
There are some proteins that are not in CHEBI
We need to standardise
Peter suggests to iterate rather than do all at once. Maybe pick a branch
Not in CHEBI: asal carnetines, and some other more detailed once
Grow hormone should have been called “definiciency”!
“Normal” values for all of these would be helpful - 
We need to be able to have the “code” encode “blood glucose level” -> is this normal?
We need to way to encode the reference ranges “these are normal values”
Nico write some suggestion on this
biological attribute + reference range normal —> maps to HPO abnormal
pyphetools has a system for doing this. needs to make it more robust

Meeting with Leigh 27 June
Add original labels as synonyms instead of replacing generated labels
Peter said that this is ok


