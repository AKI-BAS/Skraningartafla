# -*- coding: utf-8 -*-
"""Flytja skráningartöflu út í Excel (HMS útgáfa 5.03).

Les svæði (Areas) eða herbergi (Rooms) úr líkaninu, villuleitar og fyllir
afrit af skráningartöflunni: Forsíða, Matshluti, Hæðir, Einingar,
Sameign sumra og Athugasemdir. Síðan er ýtt á Reikna í Excel.
"""
__title__ = "Flytja út\nskráningartöflu"
__doc__ = ("Les svæði/herbergi úr líkaninu og fyllir út HMS skráningartöflu (5.03) í Excel. "
           "Sýnir villuleit og yfirlit í úttaksglugga.")

from skraning import export

export.run(check_only=False)
