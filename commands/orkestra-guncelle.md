---
description: "Orkestra model ve platform kaydını güncelle: keşif, fark, web araştırması, sınıflama, yeni platform ekleme, değişiklik özeti"
argument-hint: "[hizli | tam | platform | platform-ekle <ad> [--giris-var] | model <ad> | uygula --web <sonuc.json> [--onay] | uygula --platform <oneriler.json>] [--kuru] [--sef rol:efor] | \"<ad> platformunu ekledim\""
disable-model-invocation: true
---
`orkestra` skill'ini Skill aracıyla `guncelle $ARGUMENTS` argümanıyla çağır ve skill'in `references/guncelle.md` akışını uygula.
Kip boşsa `hizli`; her kip (platform hariç) araştırma planı üretir ve lider onu `references/guncelle.md` bölüm 9'a göre yürütür (web araştırması atlanmaz). Serbest metin ("X platformunu ekledim / ekleyeceğim") `platform-ekle X` sayılır. Bu komut kendi kuralını içermez; tek kaynak skill'dir.
