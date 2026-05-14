Le front est une brique standalone du system agentic. elle peut être supprimé du projet sans rien casser. elle ne doit pas créer des actions qui ne seraient pas prévu par le system agentique mais exploiter celles deja en place pour les rendre dans une interface homme machine ux design. Par exemple elle ne doit pas inventer des nouveau usages mais s'appuyer sur ce qui existe. 

 dès qu’une logique devient importante dans le dashboard, elle doit devenir vraie pour tout Marius.

Pas forcément avec la même UX partout, mais avec le même modèle métier.

-------------
Assume la task comme objet canonique
C’est probablement la bonne direction.

Si la task devient :
- l’unité de backlog
- l’unité de planification
- l’unité de lancement
- et la base des routines quand recurring=true

alors il faut l’assumer partout :
- dashboard
- CLI
- web conversationnel
- Telegram
- tools internes
---------------
Fais de la home du dashboard le résumé officiel de Marius
La home devrait incarner la vérité produit.

Elle doit répondre à :
- est-ce que le système va bien ?
- qu’est-ce qui demande mon attention ?
- qu’est-ce qui est bloqué ?
- qu’est-ce qui tourne sans moi ?
- quelle est la prochaine action utile ?

------------------
Vérifie toujours la parité d’intention entre surfaces
Pour chaque gros usage du dashboard, demande-toi :

 est-ce que la même intention existe aussi hors dashboard ?

Exemples :
- créer une task
- la planifier
- l’attacher à un projet
- créer un projet
- lancer une routine
- voir ce qui bloque
- savoir ce qui tourne

Si une intention n’est naturelle que dans le dashboard, il y a risque de désalignement.

Mon diagnostic court

Aligné
- task/routine comme base commune
- idée que le front ne doit pas inventer un autre système
- volonté de garder le runtime au centre

À surveiller
- task board qui formalise plus vite que le conversationnel
- control qui pourrait devenir un produit dans le produit
- home qui doit devenir une synthèse canonique

Le vrai risque
Pas que le dashboard soit mauvais.

Le vrai risque, c’est :

 que le dashboard pense mieux Marius que Marius hors dashboard.

---------------------

- revoir les rappel - sheduled
- pouvoir ajouter un providers dans le dashboard
- owsap gen ai securitye