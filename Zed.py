"""
© 2025 Internetrat18. All Rights Reserved.

This code is provided publicly for educational viewing and reference only.
You may not copy, redistribute, modify, or use any part of this code for any purpose
without explicit written permission from the author.
"""
import discord
from discord.ext import commands
from discord import app_commands
from discord import Interaction, ButtonStyle
from discord.ui import Button, View
import random
import time
import math

intents = discord.Intents.default()
intents.messages = True #only used for DMs
intents.message_content = True #only used for DMs
          
encounter_state = {
    "characterOrder": [],
    "characterOwners": [],
    "currentIndex": 0,
    "actionsLeft": [] #[Action, BonusAction and Reaction for each character
} #Used for all the information related to encounters. This can be called anywhere without the use of 'global encounter_state' (unless the whole variable is getting redefined)
focusMessage = None

# Define the bot with slash command support
class DnDBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="=", case_insensitive=True, intents=intents)

    async def setup_hook(self):
        #Register the slash commands globally or use guild-specific for faster testing (change using boolean below)
        devTesting = False
        if devTesting:
            print("Running in debug mode. Syncing to test guild.")
            devGuildID = 757478928653877309
            devGuild = discord.Object(id=devGuildID)
            synced = await self.tree.sync(guild=devGuild)
            print("Slash commands synced: " + str(len(synced)))
        else:
            print("Running in production mode. Syncing globally.")
            synced = await self.tree.sync()
            print("Slash commands synced: " + str(len(synced)))

# Create the bot instance
client = DnDBot()

# Event: Bot is ready
@client.event
async def on_ready():
    print("Bot is online as " + str(client.user))
    await client.change_presence(activity=discord.Game(name="DND probably"))

# Slash command: /cast
@client.tree.command(name="cast", description="Cast a spell at a target as a caster.")
@app_commands.describe(spell="The spell to cast (if multible beams write one target for each)",
                       target="The target of the spell (write a list for multible targets.)",
                       caster="The one casting the spell",
                       upcast_level="What level you wish to cast this spell (optional)",
                       advantage_override="Used for special circumstances, will override conditional (dis)advantage")
@app_commands.choices(
    advantage_override=[app_commands.Choice(name="Dis-advantage", value="disadvantage"),
                        app_commands.Choice(name="advantage", value="advantage")])
async def cast(interaction: discord.Interaction, spell: str, target: str, caster: str, upcast_level: int = 0, advantage_override: str = "none"):
    spell = spell.lower().strip()
    target = target.lower().strip()
    caster = caster.lower().strip()
    #'Sanatise' the user inputs
    if "," in target:
        completeOutputMessage = ""
        #There is a list of targets given
        for singleTarget in target.split(","):
            singleTarget = singleTarget.strip()
            OutputMessage, spellActionUsage, caster = await cast_logic(interaction, spell, singleTarget, caster, upcast_level, advantage_override)
            completeOutputMessage += OutputMessage
            completeOutputMessage += "\n" + "\n"
            #Call the logic for each, joining the messages with double newline characters
        completeOutputMessage = completeOutputMessage.strip()
        await interaction.response.send_message(completeOutputMessage)
        #remove the extra newline character and send it as one
    else:
        OutputMessage, spellActionUsage, caster = await cast_logic(interaction, spell, target, caster, upcast_level, advantage_override)
        await interaction.response.send_message(OutputMessage)
        #Otherwise, call the logic for the single target
    if spellActionUsage[1:] == "action": await encounter(interaction, "remove action", "action", caster)
    elif spellActionUsage == "bonusaction": await encounter(interaction, "remove action", "bonus action", caster) 
    elif spellActionUsage == "reaction": await encounter(interaction, "remove action", "reaction", caster)

async def cast_logic(interaction, spell: str, target: str, caster: str, upcast_level: int = 0, advantage_override: str = "none"):
    #First we gain the relevent information from the caster & target
    spellSave = ""
    damage = 0
    tempHpToApply = 0
    conditionsAlreadyPresent = ""
    targetConditionsToApply = ""
    casterConditionsToApply = ""
    crit = False
    with open("Zed\characters.csv") as characterFile:
        for line in characterFile.readlines():
            fields = line.split(",")
            fields = [s.lower() for s in fields]
            fields = [s.strip() for s in fields]
            #Split the line into fields once here to save resources on always splitting it. Also 'sanatise' it with lower() and strip()
            if fields[0].startswith(caster):
                caster = fields[0]
                #Select the line with caster info
                casterSpellAbilityIndex = 3 #3 id default for most classes 
                if fields[1].split(" ")[0] in ["cleric" , "druid", "monk", "ranger"]:
                    casterSpellAbilityIndex = 4 #4 is for WIS
                elif fields[1].split(" ")[0] in ["Bard", "Paladin", "Sorcerer", "Warlock"]:
                    casterSpellAbilityIndex = 5 #5 is for CHA
                casterSpellAbilityMod = int((int(fields[2].split("/")[casterSpellAbilityIndex])-10)/2)
                casterProfBonus = int(fields[7])
                casterSpellAttBonus = casterProfBonus + casterSpellAbilityMod
                casterSpellSaveDC = 8 + casterProfBonus + casterSpellAbilityMod
                casterLevel = float(fields[1].split(" ")[1])
                casterConditions = fields[12]
                
            if fields[0].startswith(target):
                target = fields[0]
                #Select the line with the target info
                targetStatMods = fields[3]
                targetAC = int(fields[5])
                targetProfBonus = int(fields[7])
                targetSavingThrows = fields[9]
                targetVunResImm = fields[11]
                targetConditions = fields[12]

    with open("Zed\spells.csv") as spellFile:
        for line in spellFile.readlines():
            fields = line.split(",")
            fields = [s.lower() for s in fields]
            fields = [s.strip() for s in fields]
            #Split the line into fields once here to save resources on always splitting it. Also 'sanatise' it with lower() and strip()
            if fields[0].startswith(spell):
                spell = fields[0]
                #Select the line with the spell info
                
                spellDamage = fields[3]
                if int(fields[1]) == 0 and fields[6] != "":
                    #if its a cantrip, and has 'upcast' damage, add correct damage depending on player level
                    additionalDice = 0
                    for levRequirement in fields[6].split("/"):
                        if int(levRequirement) <= casterLevel:
                            additionalDice += 1
                    #If it meets the level requirement for the bonus dice, count the additionalDice that will be added
                    spellDamage = str(int(spellDamage[0:1])+additionalDice) + spellDamage[1:]
                    #update the spell damage by adding the bonus dice
                elif upcast_level > int(fields[1]):
                    #if the upcast paramater is higher than the spell level (a valid upcast)
                    additionalDice = upcast_level - int(fields[1])
                    spellDamage = str(int(spellDamage[0:1])+additionalDice) + spellDamage[1:]
                    #Update spell damage, by adding one additonal dice for each upcast level
                spellActionUsage = fields[2]
                spellDamageType = fields[4]
                spellSave = fields[5]
                spellOnSave = fields[7]
                spellConditions = fields[8].split(" ")
                if "concentration" in casterConditions.lower() and "concentration" in fields[8].lower():
                    await interaction.response.send_message(":exclamation: You are already concentrating on a spell. This cast has been Canceled.")
                    return()
                break #So it wont continue searching the file, executing every spell that starts with the entered spell
                
    targetSaveMod = 0 #By defult
    saveType = "Unknown"
    saveDC = 0 #By defult it will always hit (for spells like haste)

    critImmune = True
    if spellSave == "ac":
        critImmune = False
        for condition in targetConditions.split(" "):
            if condition.startswith("minac"):
                targetAC = int(condition[5:]) #For spells like barkskin that set a minimum AC via a condition
        saveDC = targetAC
        saveType = "Ac"
    elif spellSave in ["str", "dex", "con", "int", "wis", "cha"]:
        #if the spell requires a stat save
        saveDC = casterSpellSaveDC
        casterSpellAttBonus = 0 #Irrelevent in this case, set to 0
        saveType = spellSave
        
        targetSaveMod = int(targetStatMods.split("/")[int(["str", "dex", "con", "int", "wis", "cha"].index(str(spellSave)))])
        if spellSave in targetSavingThrows:
            targetSaveMod += targetProfBonus

    if spellDamage != "":
        # If the spell applies damage
        totalDamage = 0
        damageBreakdown = []
        crit = False  # default unless a crit occurs
        if "+" in spellDamage and spellDamage.count("d") == spellDamage.count("+")+1:
            splitDamages = spellDamage.split("+")
            splitDamageTypes = spellDamageType.split("/")
            rollToHit = 0
            for index, damageDiceForm in enumerate(splitDamages):
                damageType = splitDamageTypes[index] if index < len(splitDamageTypes) else splitDamageTypes[-1]
                partDamage, partDamageType, rollToHit, saved, partCrit = calc_damage(damageDiceForm.strip(), casterSpellAttBonus, 0, saveDC, targetSaveMod, damageType.strip(), targetVunResImm, casterConditions+"/"+targetConditions, spellOnSave.title(), advantage_override, critImmune, rollToHit)
                totalDamage += partDamage
                damageBreakdown.append("**" + str(partDamage) + damageType.strip().title() + "** (" + damageDiceForm.strip() + ")")
                print(str(partDamage) + damageType.strip().title() + " (" + damageDiceForm.strip() + ")")
                if partCrit:
                    crit = True
            damage = totalDamage
        else: #Regular dice roll
            flatDamage = 0
            if spell.lower() in ["healing word", "player of healing", "mass healing word", "cure wounds"]: #Healing spells that add SpellcastingMod
                flatDamage = casterSpellAbilityMod
            elif "+" in spellDamage: #Regular dice roll + flat amount
                flatDamage = int(spellDamage.split("+")[1])
                spellDamage = spellDamage.split("+")[0]
            elif "+" not in spellDamage and "d" not in spellDamage: #Just a flat amount
                flatDamage = int(spellDamage)
                spellDamage = "0d0"
            damage, damageType, rollToHit, saved, crit = calc_damage(spellDamage, casterSpellAttBonus, flatDamage, saveDC, targetSaveMod, spellDamageType, targetVunResImm,casterConditions + "/" + targetConditions, spellOnSave.title(), advantage_override, critImmune)
            if spellDamage == "0d0": damageBreakdown.append("**" + str(damage*-1) + spellDamageType.title() + "** (" + str(flatDamage) + ")")
            if spellDamageType.lower() == "temphp":
                tempHpToApply = damage
                damage = 0
            elif damage > 0: damageBreakdown.append("**" + str(damage) + spellDamageType.title() + "** (" + spellDamage + spellDamageType.title() + ("+" + str(flatDamage) if flatDamage > 0 else "") + ")")
            elif damage < 0: damageBreakdown.append("**" + str(damage*-1) + spellDamageType.title() + "** (" + spellDamage + spellDamageType.title() + ("+" + str(flatDamage) if flatDamage > 0 else "") + ")")

        if crit:
            spellDamage = "+".join(splitDamages if "+" in spellDamage else [spellDamage])
    else: # If it doesn't apply damage
        if saveDC <= 0:
            saved = False
            rollToHit = 0
        else:
            rollToHit = roll_dice(1, 20, targetSaveMod)
            saved = rollToHit >= saveDC
    casterConditionsToApply = ""
    targetConditionsToApply = ""
    conditionsAlreadyPresent = ""
    if saved == False and spellConditions != "":
        for condition in spellConditions:
            if condition.startswith("#"):
                casterConditionsToApply += " " + condition[1:]
                if "concentration" in condition: #If its concentration being self-applied, give reference to the spell
                    casterConditionsToApply += ":" + spell.replace(" ", "|") + ":" + target.replace(" ", "|")
            elif condition.startswith("-"):
                condition = condition
                remove_logic(target, condition[1:])
            elif condition in targetConditions:
                conditionsAlreadyPresent += " " + condition.title()
            else:
                targetConditionsToApply += " " + condition.title()
                        
    outputMessage = "*" + caster.title() + "* has casted *" + spell.title() + "* targeting *" + target.title() + "*"
    if spellSave == "ac": outputMessage += "\n:dart: Did the spell succeed?: " + ("❌" if saved else "✅") + " (" + str(rollToHit) + "Hit vs " + str(saveDC) + "Ac)"
    elif spellSave != "Unknown" and spellSave != "": outputMessage += "\n:dart: Did the spell succeed?: " + ("❌" if saved else "✅") + " (" + str(saveDC) + "SpellDC vs " + str(rollToHit) + spellSave.title() + ")"
    #if damage > 0: outputMessage += "\n:crossed_swords: Target took a total effective dmg of: **" + str(damage) + spellDamageType.title() + "** (" + spellDamage + "+" + str(casterSpellAttBonus) + ")"
    if damage > 0: outputMessage += "\n:crossed_swords: Target took a total effective dmg of: " + " & ".join(damageBreakdown)
    if damage < 0: outputMessage += "\n:heart: Target healed a total effective amount of: " + " & ".join(damageBreakdown)
    if tempHpToApply != 0: outputMessage += "\n:blue_heart: Target was granted " + str(tempHpToApply) + " temporary HP."
    if conditionsAlreadyPresent.strip() != "": outputMessage += "\n:warning:These conditions were already present: " + conditionsAlreadyPresent.strip().title()
    if targetConditionsToApply.strip() != "": outputMessage += "\n:face_with_spiral_eyes: The following conditions were applied: " + targetConditionsToApply.strip().title()
    if "concentration" in casterConditionsToApply.strip(): outputMessage += "\n:eye: Self condiitons applied: " + casterConditionsToApply.strip().title()
    if crit is True: outputMessage += "\n:tada: CRITICAL HIT! Your damage dice was rolled twice"
    if upcast_level > 0: outputMessage += "\n:magic_wand: Attempted to upcast " + spell.title() + " to level " + str(upcast_level)
    if advantage_override != "none": outputMessage += "\n:warning:Manual (Dis)Advantage Override was given: " + advantage_override
    #Now we write the effects to the the char file updated (There is a characterBK.csv file to restore it to its original) and remove the action from the player.
    applyEffectsReturnString = apply_effects(caster, target, damage, targetConditionsToApply+"/"+casterConditionsToApply, "none", tempHpToApply)
    if "TargetZeroHp" in applyEffectsReturnString: outputMessage += "\n:skull: " + target.title() + " has reached zero(0) hit points."
    if "ConcentrationBroken" in applyEffectsReturnString: outputMessage += "\n:eye: " + target.title() + " has broken their concentration."
    return(outputMessage, spellActionUsage, caster)

def getCharacterInfo(character: str) -> tuple[dict, bool]:
    characterFound = False
    characterDict = {}
    with open("Zed\\characters.csv") as characterFile:
        for line in characterFile.readlines():
            fields = line.split(",")
            fields = [s.lower() for s in fields]
            fields = [s.strip() for s in fields]
            if fields[0].startswith(character):
                characterDict = {"name": str(fields[0]),
                                 "class": str(fields[1].split(" ")[0]),
                                 "level": float(fields[1].split(" ")[1]),
                                 "stats": [int(mod) for mod in str(fields[2]).split("/")[:6]],
                                 "statMods": [int(mod) for mod in str(fields[3]).split("/")[:6]],
                                 "HPMax": int(str(fields[4]).split("/")[0]),
                                 "HPTemp": int(str(fields[4]).split("/")[1]),
                                 "HPCurrent": int(str(fields[4]).split("/")[2]),
                                 "AC": int(fields[5]),
                                 "speed": int(fields[6]),
                                 "profBonus": int(fields[7]),
                                 "proficiencies": str(fields[8]),
                                 "savingThrows": str(fields[9] + "/").split("/")[:-1][:6],
                                 "deathSaves": str(fields[10]),
                                 "VunResImm": str(fields[11]),
                                 "vulnerabilities": str(fields[11]).split("/")[0].split(" ")[:20],
                                 "resistances": str(fields[11]).split("/")[1].split(" ")[:20],
                                 "immunities": str(fields[11]).split("/")[2].split(" ")[:20],
                                 "conditions": str(fields[12]).split(" ")}
                characterFound = True
                break
    return(characterDict, characterFound)

def getAttackInfo(attack: str) -> tuple[dict, bool]:
    attackFound = False
    attackDict = {}
    with open("Zed\\attacks.csv") as attacksFile:
        for line in attacksFile.readlines():
            fields = line.split(",")
            fields = [s.lower() for s in fields]
            fields = [s.strip() for s in fields]
            if fields[0].startswith(attack):
                attackDict = {"name": str(fields[0]),
                              "damageDice": str(fields[1] + "+").split("+")[:-1][:5],
                              "damageType": str(fields[2] + "/").split("/")[:-1][:5],
                              "class": str(fields[3]),
                              "properties": str(fields[4] + " ").split(" ")[:-1][:5],
                              "conditions": str(fields[5])}
                attackFound = True
                break
    return(attackDict, attackFound)
            
# Slash command: /Attack
@client.tree.command(name="attack", description="For all Non-magical attacks")
@app_commands.describe(attacker="The name of character who is attacking",
                       attack="The name of the attack/weapon you want to use",
                       target="The name of character who you want to attack",
                       secondary_attack="follow up attack, usually only used for sneak attacks, superiority dice attacks and duel weilding.",
                       weapon_mod="If your weapon is enchanted with a hit/damage modifier",
                       secondary_weapon_mod="If your secondary weapon is enchanted with a hit/damage modifier",
                       advantage_override="Used for special circumstances, where (dis)advantage is given outside of conditions* (*invisiility included*).")
@app_commands.choices(
    advantage_override=[app_commands.Choice(name="Dis-advantage", value="disadvantage"),
                        app_commands.Choice(name="advantage", value="advantage")])
async def attack(interaction: discord.Interaction, attacker: str, attack: str, target: str, secondary_attack: str = "none", weapon_mod: int = 0, secondary_weapon_mod: int = 0, advantage_override: str = "none"):
    #'Sanitise' the user inputs
    attack = attack.lower().strip()
    secondary_attack = secondary_attack.lower().strip()
    attacker = attacker.lower().strip()
    target = target.lower().strip()
    #Setup some varaibles.
    outputMessage, extraOutput, preferedSkill, targetConditionsToApply, attackerConditionsToApply = "", "", "", "", ""
    bonusToHit, bonusToDmg, secBonusToHit, secBonusToDmg, attackRollToHit, secAttackRollToHit = 0, 0, 0, 0, 0, 0
    attackDamages, attackDamageTypes, secAttackDamages, secAttackDamageTypes = [], [], [], []
    attackSaved, attackCrit, secAttackSaved, secAttackCrit = False, False, False, False
    #Next get the relevant information from the attacker, target, and attack files. (This will be rewriteen when SQL is integrated.)
    attackerDict, attackerFound = getCharacterInfo(attacker)
    targetDict, targetFound = getCharacterInfo(target)
    attackDict, attackFound = getAttackInfo(attack)
    secAttackDict, secAttackFound = getAttackInfo(secondary_attack)
    #If any were not found, tell the user and stop.
    if not attackerFound:
        await interaction.response.send_message("Attacker was not found, check input and try again.")
        return()
    if not targetFound:
        await interaction.response.send_message("Target was not found, check input and try again.")
        return()
    if not attackFound:
        await interaction.response.send_message("Attack was not found, check input and try again.")
        return()
    if secondary_attack != "none" and not secAttackFound:
        await interaction.response.send_message("Secondary attack was not found, check input and try again.")
        return()
    #Ensure read data is valid, this is not rigorous.
    if len(attackDict["damageType"]) > 1 and len(attackDict["damageDice"]) !=  len(attackDict["damageType"]):
        await interaction.response.send_message("The main attack has invalid damage:type ratio.")
        return()
    if "grappling" in attackerDict["conditions"] and (attackFound or secAttackFound):
        await interaction.response.send_message("Attacking while grappling a creature is not allowed. You may use /remove to stop grappling")
        return()
    if secondary_attack != "none":
        if len(secAttackDict["damageType"]) > 1 and len(secAttackDict["damageDice"]) !=  len(secAttackDict["damageType"]):
            await interaction.response.send_message("The off-hand attack has invalid damage format.")
            return()
        if ("light" not in secAttackDict["properties"] or "light" not in attackDict["properties"]) or "special" not in secAttackDict["properties"]:
            await interaction.response.send_message("That duel-weilding request was not valid.")
            return()
    #Special attacks dont need to execute the full logic, do them seperately now.
    print("CP1:" + str(attackDict["properties"]))
    if "special" in attackDict["properties"]:
        print("CP2:" + attackDict["name"])
        if attackDict["name"] == "grapple":
            print("CRETURE SIZE IS WANTED")
            if ability_check(targetDict["name"], "STR", "athletics", "none", True) >= ability_check(targetDict["name"], "DEX", "acrobatics", "none", True): #Determine if the target is better at Athletics or Acrobatics
                attackRollToHit, secAttackRollToHit, preferedSkill = ability_check(attackerDict["name"], "STR", "athletics"), ability_check(targetDict["name"], "STR", "athletics"), "Athletics"
            else: attackRollToHit, secAttackRollToHit, preferedSkill = ability_check(attackerDict["name"], "STR", "athletics"), ability_check(targetDict["name"], "DEX", "acrobatics"), "Acrobatics"
            attackSaved = False if attackRollToHit >= secAttackRollToHit else True
            outputMessage += "*" + attacker.title() + "* used *" + attack.title() + "* targeting *" + target.title() + "*"
            outputMessage += "\n:dart: Did the grapple succeed?: " + ("❌" if attackSaved else "✅") + " (" + str(attackRollToHit) + "Athletics vs " + str(secAttackRollToHit) + preferedSkill + ")"
            if not attackSaved: attackerConditionsToApply += "grappling:" + targetDict["name"]
            if not attackSaved: targetConditionsToApply += "grappled:" + attackerDict["name"]
            await interaction.response.send_message(outputMessage)
            return()
        if attackDict["name"] == "net":
            print("PLACEOLDER: NET")
            print("CRETURE SIZE IS WANTED")
    if secondary_attack != "none":
        if "special" in secAttackDict["properties"]:
            if secAttackDict["name"] == "sneak attack":
                print("PLACEOLDER: SNEAK ATTACK")
                secondary_attack = "none"
    #Now deduce the bonusToHit
    bonusToHit = weapon_mod
    if "finesse" in attackDict["properties"]: bonusToHit += max(attackerDict["statMods"][0], attackerDict["statMods"][1])
    elif attackDict["class"][1:2] == "r": bonusToHit += attackerDict["statMods"][1]
    else: bonusToHit += attackerDict["statMods"][0]
    bonusToDmg = bonusToHit
    if attackDict["class"] in attackerDict["proficiencies"] or attackDict["name"] in attackerDict["proficiencies"]: bonusToHit += attackerDict["profBonus"]
    if secAttackFound: #Similar code for secAttack:
        secBonusToHit = secondary_weapon_mod
        if "finesse" in secAttackDict["properties"]: secBonusToHit += max(attackerDict["statMods"][0], attackerDict["statMods"][1])
        elif secAttackDict["class"][1:2] == "r": secBonusToHit += attackerDict["statMods"][1]
        else: secBonusToHit += attackerDict["statMods"][0]
        secBonusToDmg = secBonusToHit
        if secAttackDict["class"] in attackerDict["proficiencies"] or secAttackDict["name"] in attackerDict["proficiencies"]: secBonusToHit += attackerDict["profBonus"]
    for condition in attackerDict["conditions"]:
        if condition.startswith("bless"):
            bonusToHit += roll_dice(1, 4, 0)
            extraOutput += "\n:book: Special effect 'Bless' triggered! (+1d4 to attack roll)"
            remove_logic(attackerDict["name"], "bless")
        if "hunters|mark" in condition:
            bonusToDmg, secBonusToDmg = bonusToDmg + roll_dice(1, 6), secBonusToDmg + roll_dice(1, 6)
            extraOutput += "\n:book: Special effect 'Hunters Mark' triggered! (+1d6 to attack(s) damage)"
    #Roll damage
    attackDamages, attackDamageTypes, attackRollToHit, attackSaved, attackCrit, attackFeedbackString = calc_damage(attackerDict["name"], targetDict["name"], attackDict["damageDice"], attackDict["damageType"], bonusToHit, bonusToDmg, targetDict["AC"], 0, "miss", advantage_override)
    if secAttackFound: secAttackDamages, secAttackDamageTypes, secAttackRollToHit, secAttackSaved, secAttackCrit, secAttackFeedbackString = calc_damage(attackerDict["name"], targetDict["name"], secAttackDict["damageDice"], secAttackDict["damageType"], secBonusToHit, secBonusToDmg, targetDict["AC"], 0, "miss", advantage_override)
    #Format output
    outputMessage += "*" + attacker.title() + "* used *" + attack.title() + "* targeting *" + target.title() + "*"
    outputMessage += "\n:dart: Did the main attack hit?: " + ("❌" if attackSaved else "✅") + " (" + str(attackRollToHit) + "Hit vs " + str(targetDict["AC"]) + "AC)"
    if attackCrit: outputMessage += "\n:tada: Your main attack CRITICAL HIT!"
    if not attackSaved and len(attackDamages) >= 1: outputMessage += "\n:crossed_swords: The main attack delt: " + " + ".join(str(attackDamages[i]) + str(attackDamageTypes[i]).title() for i in range(len(attackDamages)))
    if secAttackFound: outputMessage += "\n:dart: Did the off-hand attack hit?: " + ("❌" if secAttackSaved else "✅") + " (" + str(secAttackRollToHit) + "Hit vs " + str(targetDict["AC"]) + "AC)"
    if secAttackFound and secAttackCrit: outputMessage += "\n:tada: Your off-hand attack CRITICAL HIT!"
    if secAttackFound and not secAttackSaved and len(secAttackDamages) >= 1: outputMessage += "\n:crossed_swords: The off-hand attack delt " + str(secAttackDamages) + ":" + str(secAttackDamageTypes)
    outputMessage += extraOutput
    if advantage_override != "none": outputMessage += "\n:warning: Manual " + advantage_override.title() + " was given."
    #YET TO DO: Special attacks, apply effects, remove actions
    await interaction.response.send_message(outputMessage)
        
# Slash command: /Action
@client.tree.command(name="action", description="For actions other than attacks during combat.")
@app_commands.describe(character="The 'actionee' doing the acting.", action="The Action you want to perform.", target="Some actions require a target e.g. help or sometimes hide. Lists also work.")
@app_commands.choices(action=[app_commands.Choice(name=action, value=action) for action in ["Hide", "Help", "Dodge"][:25]])
async def action(interaction: discord.Interaction, character: str, action: str, target: str = ""):
    #first get characters (and targets) full name (for printing)
    with open("Zed\\characters.csv") as characterFile:
        for line in characterFile.readlines():
            fields = line.split(",")  #Break line into list of values
            if fields[0].lower().startswith(character.lower()):
                character = fields[0]
                if "Hidden" in fields[12]:
                    await interaction.response.send_message(":exclamation: " + character + " you are already hidden.")
                    return()
            if fields[0].lower().startswith(target.lower()) and target != "":
                target = fields[0]
    if action == "Help":
        apply_effects("None", target, 0, "Helped.1/") #Apply the helped condition for 1 turn
        await encounter(interaction, "remove action", "action", character)
        await interaction.response.send_message(target.title() + " is being helped this round.")
    elif action == "Hide":
        #Make a stealth check and contest it with a passive perception on the target (if any)
        stealthCheck = ability_check(character, "DEX", "Stealth")
        saved = False
        if target != "":
            perceptionCheck = ability_check(target, "WIS", "Perception", "None", True)
            if stealthCheck < perceptionCheck: saved = True
        if saved == False:
            apply_effects("None", character, 0, " Hidden.99/") #Apply the hidden condition for 99 turns (until they attack)
            await interaction.response.send_message(character.title() + ", you think you are hidden. ✅ (You actually are)")
        elif saved == True:
            await interaction.response.send_message(character.title() + ", you think you are hidden. ❌ (You actually are NOT)")
    elif action == "Dodge":
        apply_effects("None", target, 0, "Dodging.1/")
        await encounter(interaction, "remove action", "action", character)
        await interaction.response.send_message(character.title() + ", you focus your effort on dodging until the start of your next turn.")
        
# Slash command: /Search
@client.tree.command(name="search", description="Retrive information from the back-end database.")
@app_commands.describe(file="The name of the data table")
async def search(interaction: discord.Interaction, file: str):
    if file != "": #If the file parameter is entered, open it and print the 1st value in each line/row
        path = "Zed\\" + file.strip().title() + ".csv"
        with open(path) as csvFile:
            outputMessage = "All " + file + " saved are:"
            for line_index, line in enumerate(csvFile.readlines()[1:], start=1):
                outputMessage += "\n" + "[" + str(line_index) + "]: " + line.split(",")[0]
            await interaction.response.send_message(outputMessage)

# Slash command: /Create encounter
@client.tree.command(name="create_encounter", description="To create an encounter, usually only used by the DM/GM")
@app_commands.describe(characters="The name of all characters (+monsters) you wish to be in the encounter, in turn order. Seperate each caracter by a comma(,).", character_owners="The name(or @'s) of personel who are owners of the chracters. Have them in the same order as the characters entered.")
async def create_encounter(interaction: discord.Interaction, characters: str, character_owners: str = ""):
    characterList = characters.split(",")
    characterList = [s.lower() for s in characterList]
    characterList = [s.strip() for s in characterList]
    if character_owners != "":
        character_owners = character_owners.split(",")
        character_owners = [s.lower() for s in character_owners]
        character_owners = [s.strip() for s in character_owners]
    #Sanatise the user inputs
    with open("Zed\\characters.csv") as characterFile:
        for index, character in enumerate(characterList):
            encounter_state["actionsLeft"].append([1, 1, 1])
            for line in characterFile.readlines():
                if line.split(",")[0].lower().startswith(character):
                    characterList[index] = line.split(",")[0].lower()
            characterFile.seek(0)
            #Attempt to match the inputed character to a character in the character file.
    await interaction.response.send_message("Encounter has started.")
    await encounter(interaction, "start", characterList, character_owners)

async def encounter(interaction, command: str, info1: str = "", info2: str = ""):
    #This function will be the heart of the encounter. It will have all the variables without messing with global variables. All things related will call this.
    characterOrder = []
    characterOwners = []
    if command == "start":
        #Initalise the variables
        encounter_state["characterOrder"] = info1
        encounter_state["characterOwners"] = info2
        encounter_state["currentIndex"] = 0
        await encounter(interaction, "start turn")
    elif command == "start turn":
        encounter_state["actionsLeft"][encounter_state["currentIndex"]] = [1, 1, 1]
        outputMessage = (encounter_state["characterOrder"][encounter_state["currentIndex"]].title()
                         + " (" + encounter_state["characterOwners"][encounter_state["currentIndex"]] + ") is starting their turn."
                         + "\n:hourglass: " + encounter_state["characterOrder"][(encounter_state["currentIndex"] + 1) % len(encounter_state["characterOrder"])].title()
                         + " (" + encounter_state["characterOwners"][(encounter_state["currentIndex"] + 1) % len(encounter_state["characterOwners"])] + ")" + " has their turn next."
                         + "\n:stopwatch: You will have ten(10) minutes to use your actions."
                         + "\n:notepad_spiral: Check off your actions below as you go to keep track!")
        global focusMessage
        #Open the character to see if we can find it, if we can check if player needs death saves.
        with open("Zed\\characters.csv") as characterFile:
            for line in characterFile.readlines():
                fields = line.split(",")
                fields = [s.lower() for s in fields]
                fields = [s.strip() for s in fields]
                if fields[0].startswith(encounter_state["characterOrder"][encounter_state["currentIndex"]].lower()):
                    #Found the character
                    if int(fields[4].split("/")[2]) <= 0:
                        #If current character is 0hp, roll death saves
                        deathSaveRoll = roll_dice(1, 20)
                        deathSave = False
                        if deathSaveRoll >= 10:
                            #Apply the success
                            outputMessage += "\n:coffin: Your character is at 0hp. Your death save was a Success (" + str(deathSaveRoll) + ") :sparkles:"
                            apply_effects(encounter_state["characterOrder"][encounter_state["currentIndex"]].lower(), "None", 0, "/", DeathSave = "success")
                            #Check if the player is revived
                            if int(fields[10].split("/")[0]) >= 2:
                                #If the success was 2 and is now 3, revive the player by healing 1hp and give the player actions
                                apply_effects(encounter_state["characterOrder"][encounter_state["currentIndex"]], "None", -1, "/")
                                outputMessage += "\n:star2: Your character has been revived to 1hp."
                                focusMessage = await interaction.followup.send(outputMessage, view=ActionView())
                                return()
                            else:
                                #Otherwise, the player gets no actions and the next player goes
                                focusMessage = await interaction.followup.send(outputMessage)
                                await encounter(interaction, "end turn")
                                return()
                        elif deathSaveRoll < 10:
                            #Apply the fail
                            outputMessage += "\n:coffin: Your character is at 0hp. Your death save was a Fail (" + str(deathSaveRoll) + ") :drop_of_blood:"
                            apply_effects(encounter_state["characterOrder"][encounter_state["currentIndex"]].lower(), "None", 0, "/", DeathSave = "fail")
                            if int(fields[10].split("/")[1]) >= 2:
                                #If the fails was 2 and is now 3, remove the player from the turn order
                                indexOfCharacter = encounter_state["characterOrder"].index(fields[0].lower())
                                del encounter_state["characterOrder"][indexOfCharacter]
                                del encounter_state["characterOwners"][indexOfCharacter]
                                outputMessage += "\n:skull: Your character has died and has been removed from the turn order."
                                #Decrement the index to accout for the removeal and end turn
                                encounter_state["currentIndex"] -= 1
                            focusMessage = await interaction.followup.send(outputMessage)
                            await encounter(interaction, "end turn")
                            return()
                    elif fields[1].startswith("m-") == False: #If the character is above 0hp and not marked as monster
                        outputMessage += "\n:heart: Your player character is at " + fields[4].split("/")[2] + "hp"
                        if int(fields[4].split("/")[1]) > 0: #If player caracter as temp HP
                            outputMessage += " + " + fields[4].split("/")[1] + "temp-hp"
                        outputMessage += "."
                    for condition in fields[12].split(" "):
                        if "." in condition:
                            conditionParts = condition.split(".")
                            #If the condition is related to actions, adjust accordingly.
                            actCount, bActCount, rActCount = 1, 1, 1
                            if conditionParts[0] == "+Action":
                                actCount += 1
                            elif conditionParts[0] == "-Action":
                                actCount -= 1
                            elif conditionParts[0] == "Noreactions":
                                rActCount = 0
                            elif conditionParts[0] == "Nobonusactions":
                                bActCount = 0
                            encounter_state["actionsLeft"][encounter_state["currentIndex"]] = [actCount, bActCount, rActCount]
                            #Tick down the turns remaining
                            turnsRemaining = int(conditionParts[len(conditionParts)-1])-1
                            if turnsRemaining <= 0:
                                turnsRemaining = turnsRemaining
                                #Remove the condition if its expired
                                remove_logic(encounter_state["characterOrder"][encounter_state["currentIndex"]].title(), condition.title())
                            elif turnsRemaining > 0:
                                updatedCondition = conditionParts[0] + "." + str(turnsRemaining)
                                #If its not expired, remove the (old) condition and add the updatedCondition (with its timer ticked down)
                                print("Removing: " + condition.title() + ", from: " + encounter_state["characterOrder"][encounter_state["currentIndex"]].title() + ". Then adding: " + updatedCondition.title() + " to the same character.")
                                remove_logic(encounter_state["characterOrder"][encounter_state["currentIndex"]].title(), condition.title())
                                apply_effects("None", encounter_state["characterOrder"][encounter_state["currentIndex"]].title(), 0, " " + updatedCondition.title() + "/")
                    if len(fields[12].split(" ")) > 1: outputMessage += "\n:face_with_spiral_eyes: Your active conditions: " + str(fields[12].split(" ")[1:])
        focusMessage = await interaction.followup.send(outputMessage, view=ActionView())

    elif command == "end turn":
        encounter_state["currentIndex"] += 1
        if encounter_state["currentIndex"] >= len(encounter_state["characterOrder"]):
            encounter_state["currentIndex"] = 0
            await interaction.followup.send(":recycle: Going back to the start of the round.")
            #Reset the round of combat. This is an optional message that I will leave in for now. Adds clarity to the users.
        await encounter(interaction, "start turn")
    elif command == "remove action":
        try: #Allows /cast and /attack to be used outside of an encounter
            if info2 != "": #If a character is entered
                lowerCharacterOrderList = [item.lower() for item in encounter_state["characterOrder"]]
                print("Removing " + info1.title() + " from " + info2.lower() + ".")
                if info1 == "action":
                    if encounter_state["actionsLeft"][lowerCharacterOrderList.index(info2.lower())][0] <= 0: #If it already is 0, send a follow up message
                        message = await interaction.original_response()
                        await message.edit(content=message.content + "\n:grey_exclamation: You did not have the required " + info1.title() + " to do that (effects still applied, " + info1.title() + " still removed).")
                    encounter_state["actionsLeft"][lowerCharacterOrderList.index(info2.lower())][0] -= 1
                    #Should remove the reaction from the character entered in info2
                elif info1 == "bonus action":
                    if encounter_state["actionsLeft"][lowerCharacterOrderList.index(info2.lower())][1] == 0: #If it already is 0, send a follow up message
                        message = await interaction.original_response()
                        await message.edit(content=message.content + "\n:grey_exclamation: You did not have the required " + info1.title() + " to do that (effects still applied, " + info1.title() + " still removed).")
                    encounter_state["actionsLeft"][lowerCharacterOrderList.index(info2.lower())][1] = 0
                    #Should remove the reaction from the character entered in info2
                elif info1 == "reaction":
                    if encounter_state["actionsLeft"][lowerCharacterOrderList.index(info2.lower())][2] == 0: #If it already is 0, send a follow up message
                        message = await interaction.original_response()
                        await message.edit(content=message.content + "\n:grey_exclamation: You did not have the required " + info1.title() + " to do that (effects still applied, " + info1.title() + " still removed).")
                    encounter_state["actionsLeft"][lowerCharacterOrderList.index(info2.lower())][2] = 0
                    #Should remove the reaction from the character entered in info2
            else: #remove it from the current characters turn
                print("No character entered, removing " + info1.title() + " from current indexed character.")
                if info1 == "action":
                    encounter_state["actionsLeft"][encounter_state["currentIndex"]][0] = max(encounter_state["actionsLeft"][encounter_state["currentIndex"]][0]-1, 0)
                    #Will -1, but wont go below 0
                elif info1 == "bonus action":
                    encounter_state["actionsLeft"][encounter_state["currentIndex"]][1] = 0
                elif info1 == "reaction":
                    encounter_state["actionsLeft"][encounter_state["currentIndex"]][2] = 0
            await focusMessage.edit(view=ActionView())
        except Exception as e:
            print(str(e) + ". " + info1.title() + " could not be removed, is enounter started?")
        
class ActionView(View):
    def __init__(self):
        super().__init__(timeout=600) #Max timeout time is 15mins (900s)

        for index, item in enumerate(self.children):
            if index != 3:
                if encounter_state["actionsLeft"][encounter_state["currentIndex"]][index] <= 0:
                    item.disabled = True
        #Only allow the action buttons (action, bonus action and reaction buttons) to be clickable if they have the relevant actions left.

    @discord.ui.button(label="Action", style=ButtonStyle.primary)
    async def action(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Action button pressed, it has been marked as used.", ephemeral=True)
        # Disable the button and update the view
        button.disabled = True
        await interaction.message.edit(view=self)
    @discord.ui.button(label="BonusAction", style=ButtonStyle.secondary)
    async def bonus_action(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Bonus action button pressed, it has been marked as used.", ephemeral=True)
        # Disable the button and update the view
        button.disabled = True
        await interaction.message.edit(view=self)
    @discord.ui.button(label="Reaction", style=ButtonStyle.success)
    async def reaction(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("Reaction button pressed, it has been marked as used.", ephemeral=True)
        # Disable the button and update the view
        button.disabled = True
        await interaction.message.edit(view=self)
    @discord.ui.button(label="End Turn", style=ButtonStyle.danger)
    async def end_turn(self, interaction: Interaction, button: Button):
        await interaction.response.send_message("You have ended your turn.", ephemeral=True)
        await interaction.message.edit(view=None)  # Removes all buttons
        await encounter(interaction, "end turn")

# Slash command: /Apply
@client.tree.command(name="apply", description="Manually apply damage, healing, or conditions to a character (typicly used by DM).")
@app_commands.describe(target="The character you want to apply these effects to.",damage="The damage to apply to the target(0 for nothing, and negative for healing).",condition="Condition you wish to apply to the target",condition_duration="how many turns should the condition last (leave blank for no duration)")
@app_commands.choices(condition=[app_commands.Choice(name=cond, value=cond) for cond in ["Invisible", "Hidden", "Surprised", "Flanking", "Helped", "FaerieFire", "GuidingBolt", "Unaware", "Blinded", "Prone", "Poisoned", "Restrained", "Grappled", "Obscured", "Exhaustion3", "Silenced", "Dodging", "Cursed", "Paralyzed"][:25]])
async def apply(interaction: discord.Interaction, target: str, damage: int, condition: str = "", condition_duration: str = "0"):
    targetFound = False
    with open("Zed\characters.csv") as characterFile:
        for line in characterFile.readlines():
            fields = line.split(",") #Split the line into fields once here to save resources on always splitting it. Also 'sanatise' it with lower() and strip()
            if fields[0].lower().startswith(target.lower()):
                target = fields[0] #Find the targets full name
                targetFound = True
                break
    if not targetFound:
        await interaction.response.send_message(":exclamation: Target could not be found.")
    outputMessage = target.title() + " has "
    if int(damage) >= 0: outputMessage += "taken " + str(damage) + " damage."
    elif int(damage) < 0: outputMessage += "been healed for " + str(int(damage)*-1) + " damage."
    if condition != "":
        outputMessage += "\n" + str(condition) + " has also been applied"
        if int(condition_duration) > 0:
            outputMessage += " for " + str(int(condition_duration)) + " rounds"
            returnString = apply_effects("none", target, damage, " "+str(condition)+"."+condition_duration + "/")
        else: returnString = apply_effects("none", target, damage, " "+str(condition)+"/")
        outputMessage += "."
    else: returnString = apply_effects("none", target, damage, "/")
    if "TargetZeroHp" in returnString: outputMessage += "\n:skull: " +  target.title() + " has reached 0 HP."
    await interaction.response.send_message(outputMessage)

# Slash command: /Remove
@client.tree.command(name="remove", description="Manually remove a condition from a character (typicly used by DM).")
@app_commands.describe(target="The character you want to remove the condition from.",condition="Condition you wish to remove from the target, give none for a list of conditions on the target.")
async def remove(interaction: discord.Interaction, target: str, condition: str = ""):
    outputMessage = ""
    extraConditionsToRemove = []
    foundCondition = False
    with open("Zed\\characters.csv") as characterFile:
        characterFileContents = characterFile.readlines()
    updatedCharFileLines = []
    for line in characterFileContents:
        fields = line.split(",")
        if fields[0].lower().startswith(target.lower()):
            if condition == "": #No condition was entered
                await interaction.response.send_message("Conditions active on " + target.title() + ": " + fields[12])
                return()
            else:
                conditionList = [c.strip() for c in fields[12].split(" ")]
                for cond in conditionList:
                    if cond.lower().startswith(condition.lower()): #if it matches the condition
                        foundCondition = True
                        condition = cond
                        conditionList.remove(cond)
                        if "Ac." in cond: #If the condition modifies AC
                            acMod = int(cond[0:cond.index("Ac")])
                            fields[5] = str(int(fields[5])-acMod) #Get the acMod and remove it from the target's ac
                        if "save." in cond: #If the condition gives/removes a stat save advantage,
                            stat = cond[0:cond.index("save.")].upper() #includes the +/- at start
                            if stat.startswith("+") and stat in fields[9]: #If it adds the save, remove it (and target already is prof in the save)
                                fields[9].remove("/" + stat[1:])
                            elif stat.startswith("-"): #If it removes the save, add it
                                fields[9] += "/" + stat[1:]
                        if cond.lower().startswith("concentration"): #Removing concentration, so we also need to remove the spell effects
                            spellConcentrating = cond.split(":")[1].replace("|", " ").strip() #Get the spell that the target is concentrating on
                            spellConcentratingTarget = cond.split(":")[2].replace("|", " ").strip() #Get the target of the spell (to remove its conditions)
                            with open("Zed\\spells.csv") as spellFile:
                                for line in spellFile.readlines():
                                    if line.split(",")[0].lower() == spellConcentrating:
                                        spellConcentratingConditions = line.split(",")[8].strip() #Open the spell file, find the spell being concentrated on
                                        for concentrationCond in spellConcentratingConditions.split(" "):
                                            if concentrationCond.startswith("#"): #Remove self inflicted conditions, their not relevent here
                                                spellConcentratingConditions = spellConcentratingConditions.replace(concentrationCond, "") 
                                                spellConcentratingConditions = spellConcentratingConditions.strip()
                                            extraConditionsToRemove.append(spellConcentratingTarget + "," + concentrationCond)
                                            
                fields[12] = " ".join(conditionList)
                line = ",".join(fields)
        updatedCharFileLines.append(line)
    if not foundCondition:
        await interaction.response.send_message(target.title() + " did not have '" + condition.title() + "' present as a condition.")
        return()
    with open("Zed\\characters.csv", "w") as f:
        for line in updatedCharFileLines:
            f.write(line.strip() + "\n") #This will truncate the file (remove its contents) and write the updated lines in.

    for extraCond in extraConditionsToRemove:
        extraCondTarget = extraCond.split(",")[0]
        extraCondCond = extraCond.split(",")[1]
        remove_logic(extraCondTarget, extraCondCond)
        print("Removed extra cond: " + extraCondCond + ", from: " + extraCondTarget)
    await interaction.response.send_message(condition.title() + " has been removed from " + target.title())

def remove_logic(target: str, condition: str):
    with open("Zed\\characters.csv") as characterFile:
        characterFileContents = characterFile.readlines()
    updatedCharFileLines = []
    for line in characterFileContents:
        fields = line.split(",")
        if fields[0].lower().startswith(target.lower()):
            conditionList = [c.strip() for c in fields[12].split(" ")]
            for cond in conditionList:
                if cond.lower().startswith(condition.lower()): #if it matches the condition
                    condition = cond
                    conditionList.remove(cond)
                    if "Ac." in cond: #If the condition modifies AC
                        acMod = int(cond[0:cond.index("Ac")])
                        fields[5] = str(int(fields[5])-acMod) #Get the acMod and remove it from the target's ac
                    if "save." in cond: #If the condition gives/removes a stat save advantage,
                        stat = cond[0:cond.index("save.")].upper() #includes the +/- at start
                        if stat.startswith("+") and stat in fields[9]: #If it adds the save, remove it (and target already is prof in the save)
                            fields[9].remove("/" + stat[1:])
                        elif stat.startswith("-"): #If it removes the save, add it
                            fields[9] += "/" + stat[1:]
            fields[12] = " ".join(conditionList)
            line = ",".join(fields)
        updatedCharFileLines.append(line)
    with open("Zed\\characters.csv", "w") as f:
        for line in updatedCharFileLines:
            f.write(line.strip() + "\n") #This will truncate the file (remove its contents) and write the updated lines in.

# Create character via DM (Direct Messages) structured conversation
@client.tree.command(name="create_character", description="Create a character step-by-step for the encounter tracker.")
async def create_character(interaction: discord.Interaction):
    await interaction.response.send_message("✅ Check your DMs to begin character creation.", ephemeral=True) #Sends an immediate message
    
    user = interaction.user
    dmChannel = await user.create_dm()
    def check(m): #This filters messages so it must be from the inital user and in Tempestros DM's
        return m.author == user and m.channel == dmChannel 
    
    try:
        #Name
        await dmChannel.send("What is your character's **name**?")
        msgName = await client.wait_for('message', check=check, timeout=300)
        name = msgName.content.strip()

        #Class and Level
        await dmChannel.send("What is your **class and level**? (e.g., Wizard 9)")
        msgClassAndLevel = await client.wait_for('message', check=check, timeout=300)
        ClassLevel = msgClassAndLevel.content.strip()

        #Stats
        await dmChannel.send("Enter your **stats** in STR/DEX/CON/INT/WIS/CHA order separated by '/'. (e.g., 10/15/14/12/13/8)")
        msgStats = await client.wait_for('message', check=check, timeout=300)
        rawStats = msgStats.content.strip()
        statsList = rawStats.split('/')
        if len(statsList) != 6:
            await dmChannel.send("❌ Incorrect format. Please start over.")
            return
        modsList = [str((int(stat) - 10) // 2) for stat in statsList]
        statMods = "/".join(modsList)

        #HP
        await dmChannel.send("What is your **max HP**?")
        msgHp = await client.wait_for('message', check=check, timeout=300)
        maxHp = msgHp.content.strip()

        #AC
        await dmChannel.send("What is your **armor class (AC)**, including bonuses?")
        msgAc = await client.wait_for('message', check=check, timeout=300)
        Ac = msgAc.content.strip()

        #Speed
        await dmChannel.send("What is your **speed** (in ft)?")
        msgSpeed = await client.wait_for('message', check=check, timeout=300)
        speed = msgSpeed.content.strip()

        #Calculate proficiency bonus
        try:
            level = int(ClassLevel.split()[-1])
            if level >= 17: profBonus = 6
            elif level >= 13: profBonus = 5
            elif level >= 9: profBonus = 4
            elif level >= 5: profBonus = 3
            else: profBonus = 2
        except:
            profBonus = 2

        #Skill Proficiencies
        skillsList = ["Acrobatics", "Animal Handling", "Arcana", "Athletics", "Deception", "History", "Insight", "Intimidation", "Investigation", "Medicine", "Nature", "Perception", "Performance", "Persuasion", "Religion", "Sleight of Hand", "Stealth", "Survival"]
        skills_prompt = "\n".join([f"{i+1}. {skill}" for i, skill in enumerate(skillsList)])
        await dmChannel.send(f"Select your **skill proficiencies** by replying with numbers separated by commas.\nFor expertise, add 'E' afterwards (e.g., 3,6,12E).\nIf you have no skills, enter '0'.\n\n{skills_prompt}")
        msgProficiencies = await client.wait_for('message', check=check, timeout=300)
        entries = [x.strip().upper() for x in msgProficiencies.content.strip().split(',')]
        profSelected = []
        for entry in entries:
            expertise = entry.upper().endswith("E")
            num_part = entry[:-2] if expertise else entry
            if num_part.isdigit():
                idx = int(num_part) - 1
                if 0 <= idx < len(skillsList):
                    skill = skillsList[idx]
                    if expertise:
                        skill += "X2"
                    profSelected.append(skill)
        skillProficiencies = "/".join(profSelected)

        #Weapon Proficiencies
        await dmChannel.send("Select your **weapon proficiencies** by replying with numbers separated by commas, adding any individual weapons at the end.\n1. Simple Melee\n2. Simple Ranged\n3. Martial Melee\n4. Martial Ranged\nExample: 1,3,Longsword,Shortbow")
        msgWeapons = await client.wait_for('message', check=check, timeout=300)
        weaponProficiencies = msgWeapons.content.strip()
        weaponProficiencies = weaponProficiencies.replace("1", "SM")
        weaponProficiencies = weaponProficiencies.replace("2", "SR")
        weaponProficiencies = weaponProficiencies.replace("3", "MM")
        weaponProficiencies = weaponProficiencies.replace("4", "MR")
        weaponProficiencies = weaponProficiencies.split(",")
        proficiencies = "/".join([skillProficiencies] + weaponProficiencies)
        if proficiencies.startswith("/"):
            print("Anomoly Found. Correcting.") #Maybe happends when no skills are enteres.
            proficiencies = proficiencies[1:]

        #Saving Throws
        await dmChannel.send("List your **saving throws you are proficient in**, separated by commas. (e.g., CON,WIS)")
        msgSaved = await client.wait_for('message', check=check, timeout=300)
        savingThrows = msgSaved.content.strip()
        savingThrows = savingThrows.replace(",", "/")

        #Vun/Res/Imm
        await dmChannel.send("List your **Vulnerabilities/Resistances/Immunities** individualy seperated by space, each category separated by '/' (or enter None/None/None)")
        msgVunResImm = await client.wait_for('message', check=check, timeout=300)
        VunResImm = msgVunResImm.content.strip()

        #Confirmation preview
        character_row = f"{name},{ClassLevel},{rawStats},{statMods},{maxHp}/0/{maxHp},{Ac},{speed},{profBonus},{proficiencies},{savingThrows},0/0,{VunResImm},None"

        view = ConfirmCancelView()
        await dmChannel.send(f":pencil: Here is your generated character line:\n```{character_row}```\nIf you are unsure whether this character is correct, you can run a test attack before your encounter (making sure to /reset afterwards).\nPlease confirm or cancel to complete your character creation:", view=view)
        await view.wait()

        #If confirmed, write it in both files (saves user having to /reset for character to work).
        if view.value:
            with open("Zed\\charactersBK.csv", "a") as fBK:
                fBK.write(character_row + "\n")
            with open("Zed\\characters.csv", "a") as f:
                f.write(character_row + "\n")
            await dmChannel.send(f"✅ {name} has been saved successfully!")
        else:
            await dmChannel.send("❌ Character creation cancelled.")

    except asyncio.TimeoutError:
        await dmChannel.send(":hourglass: Timeout reached. Please run the command again if you wish to create your character.")

class ConfirmCancelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.value = None

    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        button.disabled = True
        await interaction.message.edit(view=self)
        self.stop()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        button.disabled = True
        await interaction.message.edit(view=self)
        self.stop()

@client.tree.command(name="remove_character", description="Remove a character from the database by name.")
@discord.app_commands.describe(character_name="The name of the character to remove.")
async def remove_character(interaction: discord.Interaction, character_name: str):
    try:
        with open("Zed/charactersBK.csv", "r") as f:
            lines = f.readlines()
        with open("Zed/charactersBK.csv", "w") as f:
            removed = False
            for line in lines:
                if not line.lower().startswith(character_name.lower() + ","):
                    f.write(line)
                else:
                    removed = True
                    break
        if removed:
            await interaction.response.send_message(f"✅ Successfully removed character: {character_name}. \nNote: This character is still active in your session. Please run */reset* to apply changes immediately")
        else:
            await interaction.response.send_message(f"❌ Character '{character_name}' not found in the database.")
    except Exception as e:
        await interaction.response.send_message(f"❌ An error occurred while attempting to remove the character: {e}")

# Slash command: /Reset
@client.tree.command(name="reset", description="This command will reset the character database using the backup.")
async def reset(interaction: discord.Interaction):
    try:
        # Read from backup file
        with open("Zed\\charactersBK.csv", "r") as backup_file:
            backup_data = backup_file.read()

        # Overwrite the original file with the backup data
        with open("Zed\\characters.csv", "w") as original_file:
            original_file.write(backup_data)

        await interaction.response.send_message("✅ Character database has been reset to the backup.")
    except Exception as e:
        await interaction.response.send_message("❌ Failed to reset the database: " + e)

# Slash command: /Roll
@client.tree.command(name="roll", description="Roll any number of dice!")
@app_commands.describe(dice="the dice you wish to roll, seperated by '+'. e.g. 1d20+4d6", modifier="any postitive (or negative) modifier you wish to add. e.g. +12 or -5")
async def roll(interaction: discord.Interaction, dice: str, modifier: int = 0):
    totalResult = int(modifier)
    outputMessage = "Rolling: " + dice 
    if "+" not in dice: diceArguments = 0
    else: diceArguments = len(dice.split("+"))-1
    for i in range(diceArguments+1):
        diceRoll = dice.split("+")[i]
        diceCount = int(diceRoll.split("d")[0])
        diceSides = int(diceRoll.split("d")[1])
        if diceCount == 0 or diceSides == 0: outputMessage += "\n- Nothing, no dice were rolled here. "
        else:
            outputMessage += "\n- " + str(diceSides) + "-sided dice; "
            while diceCount > 0:
                diceResult = random.randint(1, diceSides)
                totalResult += diceResult
                diceCount -= 1
                if diceCount > 0: outputMessage += str(diceResult) + ", "
                elif diceCount == 0: outputMessage += str(diceResult) + ". "
    if modifier != 0: outputMessage += "\n- Modifier: " + str(modifier) + ". "
    await interaction.response.send_message(outputMessage + "\n**Total: " + str(int(totalResult)) + "**")

# Slash command: /Roll_ability
@client.tree.command(name="roll_ability", description="This command will reset the character database using the backup.")
@app_commands.describe(roller="Character that is making the ability check.", ability="The ability you want to check, weather it be a skill or stat.", advantage_override="Give (dis)advantage?", passive="If it should return the average roll. (False by defult)")
@app_commands.choices(
    advantage_override=[app_commands.Choice(name="Dis-advantage", value="disadvantage"),
                        app_commands.Choice(name="advantage", value="advantage")],
    ability=[app_commands.Choice(name=cond, value=cond) for cond in ["STR", "DEX", "CON", "INT", "WIS", "CHA", "Athletics", "Acrobatics", "Sleight of Hand", "Stealth", "Arcana", "History", "Investigation", "Nature", "Religion", "Animal Handling", "Insight", "Medicine", "Perception", "Survival", "Deception", "Intimidation", "Performance", "Persuasion"][:25]])
async def roll_ability(interaction: discord.Interaction, roller: str, ability: str, advantage_override: str = "none", passive: bool = False):
    #'Sanitise' user inputs
    roller = roller.strip().lower()
    ability = ability.strip().lower()
    #Get the relevant information from the roller
    rollerDict, rollerFound = getCharacterInfo(roller)
    #Setup some varaibles
    releventStat = "Unknown"
    if ability not in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
        if ability == "athletics": releventStat = "STR"
        elif ability in ["acrobatics", "sleight of hand", "stealth"]: releventStat = "DEX"
        elif ability in ["arcana", "history", "investigation", "nature", "Religion"]: releventStat = "INT"
        elif ability in ["animal handling", "insight", "medicine", "perception", "survival"]: releventStat = "WIS"
        elif ability in ["deception", "intimidation", "performance", "persuasion"]: releventStat = "CHA"
    await interaction.response.send_message(roller.title() + ", your " + ability + " check rolled: " + str(ability_check(roller, releventStat, ability, advantage_override, passive)) + ".")

#function to Roll X sided dice, Y times with a Z mod
def roll_dice(dice_count: int, dice_sides: int, modifier: int = 0) -> int:
    Total = modifier
    for i in range(dice_count):
        roll = random.randint(1, dice_sides)
        Total += roll
        print("Natural roll: " + str(roll))
    return(Total)

#function to Roll ability checks/saving throws
def ability_check(roller: str, abilityStat: str, abilityCheck: str, advantage: str = "none", passive: bool = False) -> tuple[int, str]:
    #'Sanitise' inputs
    roller = roller.strip().lower()
    abilityStat = abilityStat.strip().upper()
    abilityCheck = abilityCheck.strip().lower()
    advantage = advantage.strip().lower()
    #Get the relevant information from the roller
    rollerDict, rollerFound = getCharacterInfo(roller)
    #Setup some varaibles
    extraEffects = ""
    #Dedeuce the modifier
    modifier = int(rollerDict["statMods"][["STR","DEX","CON","INT","WIS","CHA"].index(abilityStat)])
    if abilityCheck == "None": #Saving throw
        for profSavingThrow in rollerDict["savingThrows"]:
            if profSavingThrow == abilityStat: modifier += rollerDict["profBonus"] #Proficiency
        for condition in rollerDict["conditions"]:
            if condition.startswith(abilityStat): modifier += int(condition.replace(abilityStat, "")) #e.g. STR+2 condition
            if condition.startswith("bless"): #Spell specific bonus
                modifier += roll_dice(1, 4) #Consume the bonus
                extraEffects += "Bless"
                remove_logic(roller, "bless") #Remove the bonus (its consumed)
    else:
        for ability in rollerDict["proficiencies"]:
            if ability == abilityCheck: modifier += rollerDict["profBonus"] #Proficiency
            if ability == abilityCheck+"X2": modifier += rollerDict["profBonus"] #Expertise
        for condition in rollerDict["conditions"]:
            if condition.startswith(abilityCheck): modifier += int(condition.replace(abilityCheck, "")) #e.g. Stealth+10 (for 'Pass without trace')
    #Roll the ability and return result
    abilityRoll = roll_dice(1, 20, modifier)
    alternateAbilityRoll = roll_dice(1, 20, modifier)
    if advantage.lower() == "disadvantage" and alternateAbilityRoll < abilityRoll:
        abilityRoll = alternateAbilityRoll #Disadvantage, use it if its lower
        extraEffects += "Disadvantage"
    elif advantage.lower() == "advantage" and alternateAbilityRoll > abilityRoll:
        abilityRoll = alternateAbilityRoll #Advantage, use it if its higher
        extraEffects += "Advantage"
    if passive: abilityRoll = 10 + modifier #Take the average roll
    return(abilityRoll)
        
#function to roll damage (accounting for crits, resistances, immunities and vulnerabilities)
def calc_damage(attacker: str, target: str, damageDice: list, damageType: list, bonusToHit: int, bonusToDmg: int, contestDC: int, contestDCMod: int, onSave: str = "none", advantage_override: str = "none", applyCrits: bool = True, rollToHitOverride: int = 0) -> tuple[list, list, int, bool, bool, str]:
    #'Sanatise' inputs
    attacker = attacker.strip().lower()
    target = target.strip().lower()
    damageDice[:] = [str(value) for value in damageDice if "d" in value]
    damageType[:] = [str(value) for value in damageType]
    contestDC = max(contestDC, 0)
    contestDCMod = max(contestDCMod, -contestDC)
    onSave = onSave.strip().lower()
    advantage_override = advantage_override.strip().lower()
    rollToHitOverride = min(rollToHitOverride, 20)
    rollToHitOverride = max(rollToHitOverride, 0)
    #Setup some varaibles
    saved, crit, advantage, disadvantage = False, False, False, False
    rollToHit, alternateRollToHit, diceCount, diceSides = 0, 0, 0, 0
    returnDamages, returnDamageTypes = [], []
    feedbackString = ""
    attackerAdvantageConditons = ["Advantage", "Helped", "Flanking", "Hidden", "Invisible"] #Attacker has advantage if they have these
    attackerDisadvantageConditions = ["Blinded", "Frightened", "Poisoned", "Restrained", "Exhaustion3", "Disadvantage", "Prone", "Cursed"] #Attacker has disadvantage if they have these
    targetAdvantageCondtions = ["GuidingBolt", "Flanking", "Unaware", "Blinded", "Paralyzed", "Petrified", "Prone", "Restrained", "Stunned", "Unconscious", "FaerieFire", "Surprised"] #Attacker has advantage if the target has these
    targetDisadvantageConditions = ["HeavilyObscured", "Invisible", "Dodging"] #Attacker has disadvantage if te target has these
    #Gain relevent information from attacker and target.
    attackerDict, attackerFound = getCharacterInfo(attacker)
    targetDict, targetFound = getCharacterInfo(target)
    #Validate data
    if onSave not in ["miss", "half"]: onSave = "none"
    if advantage_override not in ["advantage", "disadvantage"]: advantage_override = "none"
    if len(damageType) > 1 and len(damageType) != len(damageDice):
        print("calc_damage Error: Damage dice/type format incorrect.\ndamage_dice:" + damage_dice + "\ndamageType:" + damageType)
        return()
    if not attackerFound:
        print("calc_damage Error: Attacker not found. Attacker:" + attacker)
        return()
    if not targetFound:
        print("calc_damage Error: Target not found. Target:" + target)
        return()
    #Deduce (dis)advantage
    advantage = any(cond in attackerAdvantageConditons for cond in attackerDict["conditions"])
    if not advantage: advantage = any(cond in targetAdvantageCondtions for cond in targetDict["conditions"]) #If advantage is not already true, check the targets conditions
    disadvantage = any(cond in attackerDisadvantageConditions for cond in attackerDict["conditions"])
    if not disadvantage: disadvantage = any(cond in targetDisadvantageConditions for cond in targetDict["conditions"]) #If disadvantage is not already true, ceck the targets conditions
    advantage, disadvantage = (advantage_override == "advantage"), (advantage_override == "disadvantage")
    #Roll to hit, taking into account (dis)advantage
    rollToHit = roll_dice(1, 20, bonusToHit)
    if (advantage or disadvantage) and not (advantage and disadvantage): alternateRollToHit = roll_dice(1, 20, bonusToHit)
    if advantage and not disadvantage: rollToHit = max(rollToHit, alternateRollToHit)
    if disadvantage and not advantage: rollToHit = min(rollToHit, alternateRollToHit)
    print("^Roll to hit(s).")
    crit = True if rollToHit-bonusToHit==20 and not "crit" in targetDict["immunities"] else False
    saved = True if rollToHit<contestDC+contestDCMod and not crit else False
    #Roll damage
    for index, dice in enumerate(damageDice):
        diceCount = int(dice.split("d")[0])
        diceSides = int(dice.split("d")[1])
        if crit: diceCount = diceCount*2
        damage = int(roll_dice(diceCount, diceSides, bonusToDmg))
        if bonusToDmg > 0: bonusToDmg = 0 #Apply dmg bonus once
        if saved and onSave == "miss": damage = damage*0
        if saved and onSave == "half": damage = damage/2
        if damageType[index] in targetDict["immunities"]: damage = damage*0
        elif damageType[index] in targetDict["resistances"]: damage = damage/2
        elif damageType[index] in targetDict["vulnerabilities"]: damage = damage*2
        print("Damage calculated to be: " + str(damage))
        if damageType[index] in returnDamageTypes: returnDamages[returnDamageTypes.index(damageType[index])] += damage
        elif damage > 0:
            returnDamages.append(damage)
            returnDamageTypes.append(damageType[index])
    return(returnDamages, returnDamageTypes, rollToHit, saved, crit, feedbackString)

#Function to write to character file (apply damage and conditions to attacker/caster)
def apply_effects(attacker: str, target: str, damage: int, Conditions: str, DeathSave = "none", tempHP: int = 0) -> str:
    conditionsToApply = Conditions.split("/")
    targetConditionsToApply = conditionsToApply[0]
    casterConditionsToApply = conditionsToApply[1]
    updatedCharFileLines = []
    returnString = ""
    concentrationBroken = False
    print("Applying effects. Damage: " + str(damage))
    with open("Zed\\characters.csv") as characterFile:
        characterLines = characterFile.readlines() #This stops the functions from being called within the interation of these lines to attempt to read this file while it is still open. Instead, we can save its lines to a variable and iterate through them

    for line in characterLines:
        fields = line.split(",")  #Break line into list of values
        if fields[0].strip().lower() == target.strip().lower():
            #If its the targets line
            #Applying dmg
            hpValues = fields[4].split("/") #Split the HP field ("65/0/65") into parts
            hpValues[1] = str(int(hpValues[1]) + int(tempHP))
            if int(hpValues[1]) > int(damage) and int(damage) > 0:
                #If the tempHp is higher than the dmg (and damage is positive, i.e. not healing)
                hpValues[1] = str(max(0, int(hpValues[1]) - int(damage))) #Apply damage to the temp hp
            elif int(hpValues[1]) <= int(damage) and int(damage) > 0:
                #if the target's tempHp is less than the total damage
                damage -= int(hpValues[1]) #'absorb' the tempHp
                hpValues[1] = "0" #set tempHp to none
                hpValues[2] = str(max(0, int(hpValues[2]) - int(damage))) #Apply remainder damage
            elif damage < 0: #If healing the target
                hpValues[2] = str(int(hpValues[2]) - int(damage)) #Minus the negative dmg ()
                if int(hpValues[2]) > int(hpValues[0]): hpValues[2] = hpValues[0] #Dont let the current hp exceed the max
            if int(hpValues[2]) == 0:
                returnString += "TargetZeroHp"
            fields[4] = "/".join(hpValues)
                
            #Apply New Conditions
            fields[12] = fields[12].strip() + targetConditionsToApply
            #Change other stats based on the new conditions on the target
            for cond in targetConditionsToApply.split(" "):
                if cond.strip() != "":
                    fields = apply_condition_effects(fields, cond)
            for cond in fields[12].strip().split(" "):
                if "concentration" in cond and damage > 0: #Now check if the target has concentration, then check if the save it (to keep it)
                    #Make a con save and compare it to a DC of 10 or half the dmg taken (whichever is higher)
                    savingThrow = ability_check(fields[0].strip(), "CON", "None")
                    if savingThrow < max(10, damage/2): #Failed ths save
                        spellConcentrating = cond.split(":")[1].replace("|", " ").strip() #Get the spell that the target is concentrating on
                        spellConcentratingTarget = cond.split(":")[2].replace("|", " ").strip() #Get the target of the spell (to remove its conditions)
                        concentrationBroken = True
                        returnString += "ConcentrationBroken"
                        with open("Zed\\spells.csv") as spellFile:
                            for line in spellFile.readlines():
                                if line.split(",")[0].lower() == spellConcentrating:
                                    spellConcentratingConditions = line.split(",")[8] #Open the spell file, find the spell being concentrated on
                        fields[12] = fields[12].replace(" " + str(cond.strip()), "") #remove concentration
        if fields[0].strip().lower() == attacker.strip().lower():
            #If it's the casters/attackers line
            #Apply New Conditions
            fields[12] = fields[12].strip() + casterConditionsToApply
            #Apply Death Save (if any)
            deathSaveValues = fields[10].split("/")
            if DeathSave == "success": fields[10] = str(int(deathSaveValues[0])+1) + "/" + deathSaveValues[1]
            if DeathSave == "fail": fields[10] = deathSaveValues[0] + "/" + str(int(deathSaveValues[1])+1)

        #Now do any extra things needed just before we write to the file
        if concentrationBroken == True and fields[0].lower() == spellConcentratingTarget.lower(): #Remove the conditions that the concentrating spell was appliying
            fields[12] = fields[12].strip()
            for cond in spellConcentratingConditions.split(" "):
                cond = cond.strip()
                if cond in fields[12].split(" "):
                    #First, remove its effects.
                    fields = apply_condition_effects(fields, cond, "-")
                    #Now remove the condition
                    fields[12] = fields[12].replace(" " + cond, "")
                    
        line = ",".join(fields)  #Rebuild the full line, which will later replace the original (thus updating the hp)
        #Now we add the adjusted line into a list
        updatedCharFileLines.append(line.strip())
        #With this list of strings (one string being one line of the CSV), we can write it back into the file
    with open("Zed\\characters.csv", "w") as f:
        for line in updatedCharFileLines:
            f.write(line + "\n")
            #This will truncate the file (remove its contents) and write the updated lines in.
    return(returnString)

#Function to apply, and remove conditional effects e.g. +2Ac or -DexSave
def apply_condition_effects(charactersFields: list[str], condition: str, PosNegOverride: str = "") -> str:
    #Change other stats based on the conditions on the character (+ve or -ve)
    #Apply the override if given and needed 
    if PosNegOverride == "-" and condition.startswith("+"):
        condition = "-" + condition[1:]
    elif PosNegOverride == "+" and condition.startswith("-"):
        condition = "+" + condition[1:]
    if "Ac." in condition:
        #If the condition modifies AC
        acMod = int(condition[0:condition.index("Ac")])
        charactersFields[5] = str(int(charactersFields[5])+acMod)
        #Get the acMod and add it to the target's ac
    elif "save." in condition:
        #If the condition gives/removes a stat save advantage
        stat = condition[0:condition.index("save.")].upper() #includes the +/- at start
        if stat.startswith("+"): #If it adds the save
            charactersFields[9] += "/" + stat[1:]
        elif stat.startswith("-") and stat[1:] in charactersFields[9]: #If it removes the save (and target already is prof in the save)
            charactersFields[9] = charactersFields[9].replace("/" + stat[1:], "")
    return(charactersFields)

#Ideas to add:
    """
Add Fuzzy Matching with difflib (so minor spelling mistakes don't void a command)
Graphics of some kind to make it more user-friendly and exciting to use, somewhat used in encounters
DONE ~~Manual damage/healing & conditions for people who don't use the bot (like)~~
DONE ~~Hiding, Helping, Dodgeing~~
DONE ~~Allow a list of targets to be entered~~
REJECTED(Partly) ~~Give feedback on HP values on attack~~ Reason: Most DM's wont want to reveal their monsters' HP bar to the players. Instead, if the 'character' is not marked with M- (for monster), I will give their remaining hp on turn start.
DONE ~~Add the modifier to the dmg dice text~~
DONE ~~Target yourself~~
DONE ~~Abbility checks at will~~
DONE ~~Create a character~~
DONE ~~Check and remove concentration on dmg effects (and give feedback to the user if it is) ~~
DONE ~~Expand spell list, allow for multiple damage dice sets/damage types (1 dice set for each damage type, like in the ice storm spell)~~
DONE ~~Note: Scope, No combat map, meaning no range. + As little things as hardcoded as possible~~
DONE ~~Saving throws can crit~~ also fixed saving throws being inaccurate in general, and especially inaccurate when rolling more than one damage dice
DONE ~~Manual apply not 'autocorrecting' to a target, and condition applying not working in general~~
DONE ~~Make character creation easier~~
DONE ~~Add 'effects' for spells that apply effects to the character but don't have a duration the same as conditions~~
DONE ~~I have noticed the 'remove_logic' function was removed a while ago without a replacement being given (I will fix this next). Code referencing this nonexistent function will be commented out for now, and some systems won't work as intended.~~
New character file system that includes creature type and size.
Add an autocomplete for attacks/spells, targets and attackers/casters. This is still limited to 25 option,s but can work dynamically based on what is already present in the field.
    """
# Start the bot
client.run("MY_TOKEN")
