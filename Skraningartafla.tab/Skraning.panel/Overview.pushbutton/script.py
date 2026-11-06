# -*- coding: utf-8 -*-
"""Yfirlit rýma: hrágögn úr líkaninu í venjulegt Excel skjal.

Öll herbergi, öll svæði (allar Area Schemes), hæðir, stigar, op og bílastæði,
ásamt reiknuðum rýmislínum og summu eftir eignarhaldi. Til að fylla út
skráningartöflu handvirkt og bera saman við sjálfvirka útflutninginn.
"""
__title__ = "Yfirlit\nrýma"
__doc__ = ("Flytur öll herbergi, svæði, hæðir, stiga, op og bílastæði út í venjulegt .xlsx "
           "(gildi, engar formúlur) til að fylla út skráningartöflu handvirkt og yfirfara.")

from skraning import overview

overview.run()
