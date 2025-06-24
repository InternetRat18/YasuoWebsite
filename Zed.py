import discord
from discord.ext import commands
from discord import app_commands
from discord import Interaction, ButtonStyle
from discord.ui import Button, View
import random
import time
import math

intents = discord.Intents.all()\
          
encounter_state = {
    "characterOrder": [],
    "characterOwners": [],
    "currentIndex": 0,
    "actionsLeft": [] #[Action, BonusAction, Reaction] for each character
} #Used for all the infomation to do with encounters. this can be called anywhere witout the use of 'global encounter_state' (unless the whole variable is getting redefined)
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
            devGuildID = 0 #GUILD_ID_REDACTED
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
@app_commands.describe(
    spell="The spell to cast (if multible beams write one target for each)",
    target="The target of the spell (write a list for multible targets.)",
    caster="The one casting the spell",
    upcast_level="What level you wish to cast this spell (optional)",
    advantage_override="Used for special circumstances, will override conditional (dis)advantage"
)
@app_commands.choices(
    advantage_override=[
        app_commands.Choice(name="Dis-advantage", value="disadvantage"),
        app_commands.Choice(name="advantage", value="advantage")
    ]
)
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
            completeOutputMessage += await cast_logic(interaction, spell, singleTarget, caster, upcast_level, advantage_override)
            completeOutputMessage += "\n" + "\n"
            #Call the logic for each, joining the messages with doubble newline characters
        completeOutputMessage = completeOutputMessage.strip()
        await interaction.response.send_message(completeOutputMessage)
        #remove the extra newline character and send it as one
    else:
        await interaction.response.send_message(await cast_logic(interaction, spell, target, caster, upcast_level, advantage_override))
        #Otherwise, call the logic for the single target

async def cast_logic(interaction, spell: str, target: str, caster: str, upcast_level: int = 0, advantage_override: str = "none"):
    #First we gain the relevent information from the caster & target
    with open("Zed\characters.csv") as characterFile:
        for line in characterFile.readlines():
            fields = line.split(",")
            fields = [s.lower() for s in fields]
            fields = [s.strip() for s in fields]
            #Split the line into fields once here to save resources on always spliting it. Also 'sanatise' it with lower() and strip()
            if fields[0].startswith(caster):
                caster = fields[0]
                #Select the line with caster info
                casterSpellAbilityIndex = 3 #3 id defult for most classes 
                if fields[1].split(" ")[0] in ["cleric" , "druid", "monk", "ranger"]:
                    casterSpellAbilityIndex = 4 #4 is for WIS
                elif fields[1].split(" ")[0] in ["Bard", "Paladin", "Sorcerer", "Warlock"]:
                    casterSpellAbilityIndex = 5 #5 is for CHA
                casterSpellAbilityMod = int((int(fields[2].split("/")[casterSpellAbilityIndex])-10)/2)
                casterProfBonus = int(fields[7])
                casterSpellAttBonus = casterProfBonus + casterSpellAbilityMod
                casterSpellSaveDC = 8 + casterProfBonus + casterSpellAbilityMod
                casterLevel = int(fields[1].split(" ")[1])
                casterConditions = fields[12]
                
            if fields[0].startswith(target):
                target = fields[0]
                #Select the line with target info
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
            #Split the line into fields once here to save resources on always spliting it. Also 'sanatise' it with lower() and strip()\
            if fields[0].startswith(spell):
                spell = fields[0]
                #Select the line with the spell info
                
                spellDamage = fields[3]
                if int(fields[1]) == 0 and fields[6] != "":
                    #if its a cantrip, and has 'upcast' damage add correct damage depending on player level
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
                
                targetSaveMod = 0 #By defult
                saveType = "Unknown"
                saveDC = 0 #By defult it will always hit (for spells like haste)
                
                if spellSave == "ac":
                    saveDC = targetAC
                    saveType = "Ac"
                elif spellSave in ["str", "dex", "con", "int", "wis", "cha"]:
                    #if the spell requires a stat save
                    saveDC = casterSpellSaveDC
                    saveType = spellSave
                    targetSaveMod = int(targetStatMods.split("/")[int(["str", "dex", "con", "int", "wis", "cha"].index(str(spellSave)))])
                    if spellSave in targetSavingThrows:
                        targetSaveMod += targetProfBonus
                if spellDamage != "":
                    #If the spell applies damage
                    damage, damageType, rollToHit, saved, crit = calc_damage(spellDamage, casterSpellAttBonus, 0, saveDC, targetSaveMod, spellDamageType, targetVunResImm, casterConditions+"/"+targetConditions, spellOnSave.title(), advantage_override)
                    if crit is True: spellDamage = str(int(spellDamage.split("d")[0])*2) + "d" + spellDamage.split("d")[1]
                else:
                    #If it doesnt apply damage
                    damage = 0
                    crit = False
                    if saveDC <= 0:
                        saved = False
                        rollToHit = 0
                    else:
                        rollToHit = roll_dice(1, 20, targetSaveMod)
                        if rollToHit >= saveDC:
                            saved = True
                        else:
                            saved = False
                    
                casterConditionsToApply = ""
                targetConditionsToApply = ""
                conditionsAlreadyPresent = ""
                if saved == False and spellConditions != "":
                    for condition in spellConditions:
                        if condition.startswith("#"):
                            casterConditionsToApply += " " + condition[1:]
                        elif condition in targetConditions:
                            conditionsAlreadyPresent += " " + condition.title()
                        else:
                            targetConditionsToApply += " " + condition.title()
    outputMessage = "*" + caster.title() + "* has casted *" + spell.title() + "* targeting *" + target.title() + "*"
    if spellSave == "ac": outputMessage += "\n:dart: Did the spell succeed?: " + ("❌" if saved else "✅") + " (" + str(rollToHit) + "Hit vs " + str(saveDC) + "Ac)"
    elif spellSave != "Unknown" and spellSave != "": outputMessage += "\n:dart: Did the spell succeed?: " + ("❌" if saved else "✅") + " (" + str(saveDC) + "SpellDC vs " + str(rollToHit) + spellSave.title() + ")"
    if damage > 0: outputMessage += "\n:crossed_swords: Target took a total effective dmg of: **" + str(damage) + spellDamageType.title() + "** (" + spellDamage + "+" + str(casterSpellAttBonus) + ")"
    if conditionsAlreadyPresent.strip() != "": outputMessage += "\n:warning:These conditions were already present: " + conditionsAlreadyPresent.strip().title()
    if targetConditionsToApply.strip() != "": outputMessage += "\n:face_with_spiral_eyes: The following conditions were applied: " + targetConditionsToApply.strip().title()
    if "concentration" in casterConditionsToApply.strip(): outputMessage += "\n:eye: Self condiitons applied: " + casterConditionsToApply.strip().title()
    if crit is True: outputMessage += "\n:tada: CRITICAL HIT! Your damage dice was rolled twice"
    if upcast_level > 0: outputMessage += "\n:magic_wand: Attempted  to upcast " + spell.title() + " to level " + str(upcast_level)
    if advantage_override != "none": outputMessage += "\n:warning:Manual (Dis)Advantage Override was given: " + advantage_override
    #Now we write the effects to the the char file updated (There is a characterBK.csv file to restore it to its original) and remove the action from the player.
    if apply_effects(caster, target, damage, targetConditionsToApply+"/"+casterConditionsToApply): outputMessage += "\n:skull: " + target.title() + " has reached zero(0) hit points."
    if spellActionUsage[1:] == "action": await encounter(interaction, "remove action", "action")
    elif spellActionUsage == "bonusaction": await encounter(interaction, "remove action", "bonus action") 
    elif spellActionUsage == "reaction": await encounter(interaction, "remove action", "reaction")
    return(outputMessage)

# Slash command: /Attack
@client.tree.command(name="attack", description="For all Non-magical attacks")
@app_commands.describe(
    attacker="The name of character who is attacking",
    attack="The name of the attack/weapon you want to use",
    target="The name of character who you want to attack",
    secondary_attack="follow up attack, usually only used for sneak attacks, superiority dice attacks and duel weilding.",
    weapon_mod="If your weapon is enchanted with a hit/damage modifier",
    secondary_weapon_mod="If your secondary weapon is enchanted with a hit/damage modifier",
    advantage_override="Used for special circumstances, where (dis)advantage is given outside of conditions* (*invisiility included*)."
)
@app_commands.choices(
    weapon_mod=[
        app_commands.Choice(name="+1", value="1"),
        app_commands.Choice(name="+2", value="2"),
        app_commands.Choice(name="+3", value="3")],
    secondary_weapon_mod=[
        app_commands.Choice(name="+1", value="1"),
        app_commands.Choice(name="+2", value="2"),
        app_commands.Choice(name="+3", value="3")],
    advantage_override=[
        app_commands.Choice(name="Dis-advantage", value="disadvantage"),
        app_commands.Choice(name="advantage", value="advantage")
    ]
)
async def attack(interaction: discord.Interaction, attacker: str, attack: str, target: str, secondary_attack: str = "none", weapon_mod: str = "0", secondary_weapon_mod: str = "0", advantage_override: str = "none"):
    attack = attack.lower().strip()
    secondary_attack = secondary_attack.lower().strip()
    attacker = attacker.lower().strip()
    target = target.lower().strip()
    #'Sanatise' the user inputs
    damageTotal = 0
    damageDiceTotal = ""
    seccondaryDamageDiceTotal = ""
    attackerConditionsToApply = ""
    targetConditionsToApply = ""
    #First we gain the relevent information from the attacker & target
    with open("Zed\\characters.csv") as characterFile:
        for line in characterFile.readlines():
            fields = line.split(",")
            fields = [s.lower() for s in fields]
            fields = [s.strip() for s in fields]
            #Split the line into fields once here to save resources on always spliting it. Also 'sanatise' it with lower() and strip()
            if fields[0].startswith(attacker):
                attacker = fields[0]
                #Attacker line
                attackerClass = fields[1].split(" ")[0]
                attackerLevel = int(fields[1].split(" ")[1])
                attackerStatMods = fields[3]
                attackerProfBonus = int(fields[7])
                attackerProficiencies = fields[8]
                attackerConditions = fields[12]
                
            if fields[0].startswith(target):
                target = fields[0]
                #Target line
                targetStatMods = fields[3]
                targetAC = int(fields[5])
                targetProfBonus = int(fields[7])
                targetProficiencies = fields[8]
                targetVunResImm = line.split(",")[11]
                targetVulnerabilities = targetVunResImm[0]
                targetResistances = targetVunResImm[1]
                targetImmunities = targetVunResImm[2]
                targetConditions = fields[12]
                
    
    with open("Zed\\attacks.csv") as attackFile:
        for line in attackFile.readlines():
            fields = line.split(",")
            fields = [s.lower() for s in fields]
            fields = [s.strip() for s in fields]
            #Split the line into fields once here to save resources on always spliting it. Also 'sanatise' it with lower() and strip()
            if fields[0].startswith(attack) is True and "special" not in fields[3] and "secondaryattack" not in fields[3] and fields[1] != "":
                attack = fields[0]
                #If its the selected and valid attack, has damage. Attacks marked as special will be delt with seperately. Attacks marked with SecondaryAttack can only be used as an optional extra attack. This is the execution of the main attack/weapon. Also 
                attackProperties = fields[3]
                bonusToHit = int(weapon_mod)
                bonusToDmg = 0
                damageType = fields[2]

                #Calculate te bonus to the hit roll
                strMod = attackerStatMods.split("/")[0]
                dexMod = attackerStatMods.split("/")[1]
                strMod, dexMod = int(strMod), int(dexMod)
                if "finesse" in attackProperties:
                    bonusToHit += max(strMod, dexMod)
                elif fields[3][1:2] == "R":
                    #Ranged Attack
                    bonusToHit += dexMod
                else:
                    bonusToHit += strMod
                bonusToDmg = bonusToHit
                if fields[3].split(" ")[0] in attackerProficiencies.split("/") or fields[0] in attackerProficiencies.split("/"):
                    #If attacker is proficient in the attack/weapon
                    bonusToHit += attackerProfBonus
                
                damage, damageType, rollToHit, saved, crit = calc_damage(fields[1], bonusToHit, bonusToDmg, targetAC, 0, damageType, targetVunResImm, attackerConditions+"/"+targetConditions, "Miss", advantage_override)
                damageTotal += damage
                if crit is False: damageDiceTotal += fields[1] + damageType.title() + "+" + str(bonusToDmg) + "+"
                elif crit is True: damageDiceTotal += str(int(fields[1].split("d")[0])*2) + "d" + fields[1].split("d")[1] + damageType.title() + "+" + str(bonusToDmg) + "+"
                #Count the total damage excusively for writing bback the the (character) file
                
            if fields[0].startswith(secondary_attack) is True and "special" not in fields[3]:
                secondary_attack = fields[0]
                #if secondary attack is entered, and not a special attack (i.e. attacker is duelweilding)
                secondaryAttackType = "off-hand" #Used in interaction response
                secondaryAttackProperties = fields[3]
                bonusToHit = int(secondary_weapon_mod)
                bonusToDmg = 0
                secondaryAttackDamageType = fields[2]

                #Calculate te bonus to the hit roll
                strMod = attackerStatMods.split("/")[0]
                dexMod = attackerStatMods.split("/")[1]
                strMod, dexMod = int(strMod), int(dexMod)
                if "finesse" in secondaryAttackProperties:
                    bonusToHit += max(strMod, dexMod)
                elif fields[3][1:2] == "R":
                    #Ranged Attack
                    bonusToHit += dexMod
                else:
                    bonusToHit += strMod
                bonusToDmg = bonusToHit
                if fields[3].split(" ")[0] in attackerProficiencies.split("/"):
                    #If attacker is proficient in the attack/weapon
                    bonusToHit += attackerProfBonus

                secondaryAttackDamage, secondaryAttackDamageType, secondaryAttackRollToHit, secondaryAttackSaved, secondaryAttackCrit = calc_damage(fields[1], bonusToHit, bonusToDmg, targetAC, 0, secondaryAttackDamageType, targetVunResImm, attackerConditions+"/"+targetConditions, "Miss", advantage_override)
                damageTotal += secondaryAttackDamage
                if secondaryAttackCrit is False: seccondaryDamageDiceTotal += fields[1] + secondaryAttackDamageType.title() + "+" + str(bonusToDmg) + "+"
                elif secondaryAttackCrit is True: seccondaryDamageDiceTotal += str(int(fields[1].split("d")[0])*2) + "d" + fields[1].split("d")[1] + secondaryAttackDamageType.title() + "+" + str(bonusToDmg) + "+"
                
            elif fields[0].startswith(secondary_attack) is True and "special" in fields[3]:
                #If the seccondary attack is a special attack, these require unique logic and thus is easier to hard code them, especily due to them being so few 'special' attacks.
                secondary_attack = fields[0]
                if secondary_attack == "sneak attack":
                    #If the attack is marked as 'sneak attack' we will make sure the attacker is able to use it. Because this attack relies to heavily on the main attack attrabutes we will do the logic for this after this whole file has been read.
                    if attackerClass != "rogue":
                        await interaction.response.send_message(":exclamation: Only rogues can use sneak attack.")
                        return()

            if fields[0].startswith(attack) is True and "special" in fields[3] and "secondaryattack" not in fields[3]:
                #Do the logic for primary special attacks entered here. Each one is unique and will be hard coded due to this and how few of them there are. Special secondary attacks will be dont outside of this open() statement.
                attack = fields[0]
                if attack == "grapple":
                    #Grapple special attack
                    if "grappling" in attackerConditions:
                        await interaction.response.send_message(":exclamation: You are already grappling something.")
                        return()
                    elif "grappled" in targetConditions:
                        await interaction.response.send_message(":exclamation: That target is already grappled.")
                        return()
                    attackProperties = "light" #Allows the use of an off-hand weapon
                    attackerStrMod = int(attackerStatMods.split("/")[0])
                    targetAthleticsMod = int(targetStatMods.split("/")[0])
                    targetAcrobaticsMod = int(targetStatMods.split("/")[1])
                    
                    #Roll the attacker Athletics check
                    if "athletics" in attackerProficiencies:
                        attackerAthleticsCheck = roll_dice(1, 20, attackerStrMod+attackerProfBonus)
                    else:
                        attackerAthleticsCheck = roll_dice(1, 20, attackerStrMod)
                    if "athletics" in targetProficiencies: targetAthleticsMod += targetProfBonus
                    if "acrobatics" in targetProficiencies: targetAcrobaticsMod += targetProfBonus
                    targetContestRoll = roll_dice(1, 20, max(targetAthleticsMod, targetAcrobaticsMod))
                    if attackerAthleticsCheck >= targetContestRoll:
                        saved = False
                        attackerConditionsToApply += " Grappling:" + target.title()
                        targetConditionsToApply += " Grappled"
                        
                    else:
                        saved = True
                    damage = 0
                    crit = False
                    grappleSkill = ""
                    if targetAcrobaticsMod > targetAthleticsMod:
                        grappleSkill = "acrobatics"
                    else:
                        grappleSkill = "athletics"
                elif attack == "net":
                    damage = 0
                    crit = False
                    attackMod = int(attackerStatMods.split("/")[1])
                    if "mr" in attackerProficiencies:
                        attackMod += attackerProfBonus
                    rollToHit = roll_dice(1, 20, attackMod)
                    if rollToHit >= targetAC:
                        saved = False
                        targetConditionsToApply += " Restrained"
                    else:
                        saved = True
                        
    #Do the logic for secondary special attacks now as they rely on the main attack attrabutes.
    if secondary_attack == "sneak attack":
        secondary_attack = "none"
        if saved == False:
            #If the main attack hit
            sneakAttackDiceCount = int(float((attackerLevel+1)/2))
            if crit is False:
                sneakAttackDamage = roll_dice(sneakAttackDiceCount, 6, 0)
                damageDiceTotal += str(sneakAttackDiceCount) + "d6" + damageType.title() + "+"
            elif crit is True:
                damageDiceTotal += str(sneakAttackDiceCount*2) + "d6" + damageType.title() + "+"
                sneakAttackDamage = roll_dice(sneakAttackDiceCount*2, 6, 0)
            damage += sneakAttackDamage
            damageTotal += sneakAttackDamage
                
    #Quick check to see if duel weilding was used it was valid
    if secondary_attack != "none" and attack != "grapple" and attack != "net":
        #If secondary attack was entered (some special attacks dont want this to trigger, thus secondary_attack may = none, even if one was entered at this point). If grappled was used, the secondary attack wont get advantage as it should due to effects being applied at the end of this code, so dont let it happen.
        attackProperties = attackProperties.split(" ")
        secondaryAttackProperties = secondaryAttackProperties.split(" ")
        if "light" not in attackProperties or ("light" not in secondaryAttackProperties and "special" not in secondaryAttackProperties):
            await interaction.response.send_message(":exclamation: That duel weilding request is not valid.")
            return()
        #If it was invalid, say so and stop the execution of further code. We will now format the output message for duel weilding
        outputMessage = "*" + attacker.title() + "* has used *" + attack.title() + "*&*" + secondary_attack.title() + "* targeting *" + target.title() + "*"
        if attack != "grapple": outputMessage += "\n:dart: Did the main attack hit?: " + ("✅" if not saved else "❌") + " (" + str(rollToHit) + "Hit vs " + str(targetAC) + "Ac)"
        elif attack == "grapple": outputMessage += "\n:dart: Did the Grapple succeed?: " + ("✅" if not saved else "❌") + " (" + str(attackerAthleticsCheck) + "Athletics vs" + str(targetAC) + "Ac)"
        outputMessage += "\n:dart: Did the off-hand attack hit?: " + ("✅" if not secondaryAttackSaved else "❌") + " (" + str(secondaryAttackRollToHit) + "Hit vs " + str(targetAC) + "Ac)"
        if damageTotal > 0 and damageType == secondaryAttackDamageType: outputMessage += "\n:crossed_swords: Target took a total effective dmg of: **" + str(damage+secondaryAttackDamage) + damageType.title() + "**"
        elif damageTotal > 0: outputMessage += "\n:crossed_swords: Target took a total effective dmg of: **" + str(damage) + damageType.title() + "** & **" + str(secondaryAttackDamage) + secondaryAttackDamageType.title() + "**"
        if not saved: outputMessage += " (" + damageDiceTotal[:-1] + ")"
        if not saved and not secondaryAttackSaved: outputMessage += "+"
        if not secondaryAttackSaved: outputMessage += "(" + damageDiceTotal[:-1] + ")"
        if crit is True: outputMessage += "\n:tada: CRITICAL HIT! Your main attack damage dice was rolled twice"
        if secondaryAttackCrit is True: outputMessage += "\n:tada: CRITICAL HIT! Your off-hand attack damage dice was rolled twice"
        if targetConditionsToApply != "": outputMessage +="\n:face_with_spiral_eyes: The following conditions were applied:" + targetConditionsToApply
        if advantage_override != "none": outputMessage += "\n:warning:Manual (Dis)Advantage Override was given: " + advantage_override
        if apply_effects(attacker, target, damageTotal, targetConditionsToApply + "/" + attackerConditionsToApply): outputMessage += "\n:skull: " + target.title() + " has reached zero(0) hit points."
        await interaction.response.send_message(outputMessage)
        await encounter(interaction, "remove action", "action")
        await encounter(interaction, "remove action", "bonus action") 
    else:
        #No secondary attack was given and the attack wasnt a grapple
        outputMessage = "*" + attacker.title() + "* has used *" + attack.title() + "* targeting *" + target.title() + "*"
        if attack != "grapple": outputMessage += "\n:dart: Did the attack hit?: " + ("✅" if not saved else "❌") + " (" + str(rollToHit) + "Hit vs " + str(targetAC) + "Ac)"
        elif attack == "grapple": outputMessage += "\n:dart: Did the Grapple succeed?: " + ("✅" if not saved else "❌") + " (" + str(attackerAthleticsCheck) + "Athletics vs " + str(targetContestRoll) + grappleSkill.title() + ")"
        if damage > 0: outputMessage += "\n:crossed_swords: Target took a total effective dmg of: **" + str(damage) + damageType.title() + "** (" + damageDiceTotal[:-1] + ")"
        if crit is True: outputMessage += "\n:tada: CRITICAL HIT! Your damage dice was rolled twice"
        if targetConditionsToApply != "": outputMessage +="\n:face_with_spiral_eyes: The following conditions were applied:" + targetConditionsToApply
        if advantage_override != "none": outputMessage += "\n:warning:Manual (Dis)Advantage Override was given: " + advantage_override
        if secondary_attack != "none":
            if attack == "grapple": outputMessage += "\n:warning: Secondary attacks used while attemping a grapple may not gain advantage. Your secondary attack has been canceled."
            if attack == "net": outputMessage += "\n:warning: After using the net attack, you may not use any other attacks this turn."
            damageTotal -= secondaryAttackDamage
        if apply_effects(attacker, target, damageTotal, targetConditionsToApply + "/" + attackerConditionsToApply): outputMessage += "\n:skull: " + target.title() + " has reached zero(0) hit points."
        await interaction.response.send_message(outputMessage)
        await encounter(interaction, "remove action", "action")
    #The effects were written to the the char file updated (There is a characterBK.csv file to restore it to its original) and the action removed from the player.
    
# Slash command: /Action
@client.tree.command(name="action", description="For actions other than attacks during combat.")
@app_commands.describe(
    character="The 'actionee' doing the acting.",
    action="The Action you want to perform.",
    target="Some actions require a target e.g. help or sometimes hide. Lists also work."
)
@app_commands.choices(
    action=[
        app_commands.Choice(name=action, value=action) for action in ["Hide", "Help", "Dodge"][:25]  # must be ≤25
        ]
)
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
        await encounter(interaction, "remove action", "action")
        await interaction.response.send_message(target.title() + " is being helped this round.")
    elif action == "Hide":
        #Make a stealth check and contest it with a passive perceptoion on the target (if any)
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
        await encounter(interaction, "remove action", "action")
        await interaction.response.send_message(character.title() + ", you focus your effort on dodging until the start of your next turn.")
        
# Slash command: /Search
@client.tree.command(name="search", description="Retrive information from the back-end database.")
@app_commands.describe(
    file="The name of the data table"
)
async def search(interaction: discord.Interaction, file: str):
    if file != "": #If the file paramater is entered, open it and print the 1st value in each line/row
        path = "Zed\\" + file.strip().title() + ".csv"
        with open(path) as csvFile:
            outputMessage = "All " + file + " saved are:"
            for line_index, line in enumerate(csvFile.readlines()[1:], start=1):
                outputMessage += "\n" + "[" + str(line_index) + "]: " + line.split(",")[0]
            await interaction.response.send_message(outputMessage)

# Slash command: /Create encounter
@client.tree.command(name="create_encounter", description="To create an encounter, usually only used by the DM/GM")
@app_commands.describe(
    characters="The name of all characters (+monsters) you wish to be in the encounter, in turn order. Seperate each caracter by a comma(,).",
    character_owners="The name(or @'s) of personel who are owners of the chracters. Have them in the same order as the characters entered."
)
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
    #This function will be the heart of the encounter. It will have all the variables without messing with global varaiables. All things related will call this.
    characterOrder = []
    characterOwners = []
    if command == "start":
        #Initalise the varaibles
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
                         + "\n:stopwatch: You will have five minutes to use your actions."
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
                            #Check if player is revived
                            if int(fields[10].split("/")[0]) >= 2:
                                #If the success' was 2 and is now 3, revive the player by healing 1hp and give the player actions
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
                            if conditionParts[0] == "+Action":
                                encounter_state["actionsLeft"][encounter_state["currentIndex"]] = [2, 1, 1]
                            elif conditionParts[0] == "-Action":
                                encounter_state["actionsLeft"][encounter_state["currentIndex"]] = [0, 1, 1]
                            #Tick down the turns remaining
                            turnsRemaining = int(conditionParts[len(conditionParts)-1])-1
                            if turnsRemaining <= 0:
                                #Remove the condition
                                remove_logic(encounter_state["characterOrder"][encounter_state["currentIndex"]].title(), condition.title())
                            elif turnsRemaining > 0:
                                updatedCondition = conditionParts[0] + "." + str(turnsRemaining)
                                #Remove the condition and add the updatedCondition
                                remove_logic(encounter_state["characterOrder"][encounter_state["currentIndex"]].title(), condition.title())
                                apply_effects("None", encounter_state["characterOrder"][encounter_state["currentIndex"]].title(), 0, " " + updatedCondition.title() + "/")
                    if len(fields[12].split(" ")) > 1: outputMessage += "\n:face_with_spiral_eyes: Your active conditions: " + str(fields[12].split(" ")[1:])
        focusMessage = await interaction.followup.send(outputMessage, view=ActionView())

    elif command == "end turn":
        encounter_state["currentIndex"] += 1
        if encounter_state["currentIndex"] >= len(encounter_state["characterOrder"]):
            encounter_state["currentIndex"] = 0
            await interaction.followup.send(":recycle: Going back to the start of the round.")
            #Reset the round of combat. This is an optinal message that I will leave in for now. Adds clarity to the users.
        await encounter(interaction, "start turn")
    elif command == "remove action":
        try: #Allows /cast and /attack to be used outside of an encounter
            if info1 == "action":
                encounter_state["actionsLeft"][encounter_state["currentIndex"]][0] = max(encounter_state["actionsLeft"][encounter_state["currentIndex"]][0]-1, 0)
                #Will -1, but wont go below 0
            elif info1 == "bonus action":
                encounter_state["actionsLeft"][encounter_state["currentIndex"]][1] = 0
            elif info1 == "reaction":
                encounter_state["actionsLeft"][encounter_state["currentIndex"]][2] = 0
            await focusMessage.edit(view=ActionView())
        except Exception as e:
            print(str(e) + "Action could not be removed, is enounter started?")
        
class ActionView(View):
    def __init__(self):
        super().__init__(timeout=300) #Max timeout time is 15mins (900s)

        for index, item in enumerate(self.children):
            if index != 3:
                if encounter_state["actionsLeft"][encounter_state["currentIndex"]][index] == 0:
                    item.disabled = True
        #Only allow the action buttons (action, bonus action and reaction buttons) to be clickable if they have the relevent actions left.

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
@app_commands.describe(
    target="The character you want to apply these effects to.",
    damage="The damage to apply to the target(0 for nothing, and negative for healing).",
    condition="Condition you wish to apply to the target",
    condition_duration="how many turns should the condition last (leave blank for no duration)"
)
@app_commands.choices(
    condition=[
        app_commands.Choice(name=cond, value=cond) for cond in ["Invisible", "Hidden", "Surprised", "Flanking", "Helped", "FaerieFire", "GuidingBolt", "Unaware", "Blinded", "Prone", "Poisoned", "Restrained", "Grappled", "Obscured", "Exhaustion", "Silenced", "Dodging"][:25]  # must be ≤25
        ]
)
async def apply(interaction: discord.Interaction, target: str, damage: str, condition: str = "", condition_duration: str = "99"):
    apply_effects("none", target, damage, str(condition) + "." + condition_duration + "/")
    outputMessage = "The target has "
    if int(damage) >= 0: outputMessage += "taken " + damage + " damage."
    elif int(damage) < 0: outputMessage += "been healed for " + str(int(damage)*-1) + " damage."
    if condition != "":
        outputMessage += "\n" + str(condition) + " has also been applied"
        if int(condition_duration) > 0: outputMessage += " for " + str(int(condition_duration)) + " rounds"
        outputMessage += "."
    await interaction.response.send_message(outputMessage)

# Slash command: /Remove
@client.tree.command(name="remove", description="Manually remove a condition from a character (typicly used by DM).")
@app_commands.describe(
    target="The character you want to remove the condition from.",
    condition="Condition you wish to remove from the target, give none for a list of conditions on the target."
)
async def remove(interaction: discord.Interaction, target: str, condition: str = ""):
    outputMessage = ""
    outputMessage += str(remove_logic(target, condition))
    #Have it seperate so other commands can remove conditions too
    if outputMessage == "" or outputMessage == "None": outputMessage = condition.title() + " has been removed from " + target.title()
    await interaction.response.send_message(outputMessage)
    
def remove_logic(target: str, condition: str = ""):
    with open("Zed\\characters.csv") as characterFile:
        updatedCharFileLines = []
        for line in characterFile.readlines():
            fields = line.split(",")
            if fields[0].lower().startswith(target.lower()):
                if condition == "":
                    #No condition was entered
                    return("Conditions active on " + target.title() + ": " + fields[12])
                else:
                    conditionList = [c.strip() for c in fields[12].split(" ")]
                    for cond in conditionList:
                        if "Ac." in cond:
                            #If the condition modifies AC
                            acMod = int(cond[0:cond.index("Ac")])
                            fields[5] = str(int(fields[5])-acMod)
                            #Get the acMod and remove it to the targets ac
                        if "save." in cond:
                            #If the condition gives/removes a stat save advantage
                            stat = cond[0:cond.index("save.")].upper() #includes the +/- at start
                            if stat.startswith("+") and stat in fields[9]: #If it adds the save, remove it (and target already is prof in the save)
                                fields[9].remove("/" + stat[1:])
                            elif stat.startswith("-"): #If it removes the save, add it
                                fields[9] += "/" + stat[1:]
                    if condition in conditionList:
                        conditionList.remove(condition)
                    fields[12] = " ".join(conditionList)
                    line = ",".join(fields)
            updatedCharFileLines.append(line)
    with open("Zed\\characters.csv", "w") as f:
        for line in updatedCharFileLines:
            f.write(line.strip() + "\n")
            #This will truncate the file (remove its contents) and write the updated lines in.

# Slash command: /Create Character (&Monster)
@client.tree.command(name="create_character", description="To create a character for players (&Monsters for DM's). Very sensitive, please follow instructions") 
@app_commands.describe(#These discriptions are limited to 100characters and 9 paramaters
    name="The name of character (or monster)",
    character_class="The name of the class your character is (DM's: Monsters add 'M-' beforehand followed by the type of creature)",
    character_level="The level of your character (DM's: Use this for the CR of your monster, in decimal value)",
    stats="The numerical stats of your character in this format: 'STR/DEX/CON/INT/WIS/CHA'",
    max_hp="The maximum hit points your character can have",
    armor_class="The armor class of your character (with bonuses)",
    proficiencies="A list of proficiencies, seperated by '/'. Name of weapon/skill. 'SM' = simple melee etc",
    saving_throws="The list of saving throws you are proficient in, seperated by '/'",
    vun_res_imm="A list of Vun/Res/Imm seperated by '/' and individual types seperated by space"
)
async def create_character(interaction: discord.Interaction, name: str, character_class: str, character_level: int, stats: str, max_hp: int, armor_class: int, proficiencies: str = "", saving_throws: str = "", vun_res_imm: str = ""):
    #First sanatise the user inputs
    name = name.strip()
    character_class = character_class.strip()
    stats = stats.strip()
    proficiencies = proficiencies.strip()
    saving_throws = saving_throws.strip()
    vun_res_imm = vun_res_imm.strip()
    #Then derive Prof bonus from character level
    profBonus = 2
    if character_level >= 17: profBonus = 6
    elif character_level >= 13: profBonus = 5
    elif character_level >= 9: profBonus = 4
    elif character_level >= 5: profBonus = 3
    #Now generate stat modifiers based on stats
    statMods = ""
    for stat in stats.split("/"): #Rounding down
        statMods += str(int((int(stat)-10)/2)) + "/"
    statMods = statMods[:-1] #move the extra '/'
    #We now should have all the info to write to the (backup) file. Next, santatise user inputs
    # Then format the Row and append it to the Bk file, then respond to the user
    newRow = [name, character_class + " " + str(character_level), stats, statMods, str(max_hp) + "/0/" + str(max_hp), str(armor_class), "30", str(profBonus), proficiencies, saving_throws, "0/0", vun_res_imm, "None"]
    with open("Zed\\charactersBK.csv", "a") as characterFileBK:
        characterFileBK.write(",".join(newRow) + "\n")
    await interaction.response.send_message(":pencil: " + name + " has been added the database, a reset is needed for it to show properly.")
    

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

# Slash command: /Roll_ability
@client.tree.command(name="roll_ability", description="This command will reset the character database using the backup.")
@app_commands.describe(
    roller="Character that is making the ability check.",
    ability="The ability you want to check, weather it be a skill or stat.",
    advantage_override="Give (dis)advantage?"
)
@app_commands.choices(
    advantage_override=[
        app_commands.Choice(name="Dis-advantage", value="disadvantage"),
        app_commands.Choice(name="advantage", value="advantage")
    ],
    ability=[
        app_commands.Choice(name=cond, value=cond) for cond in ["STR", "DEX", "CON", "INT", "WIS", "CHA", "Athletics", "Acrobatics", "Sleight of Hand", "Stealth", "Arcana", "History", "Investigation", "Nature", "Religion", "Animal Handling", "Insight", "Medicine", "Perception", "Survival", "Deception", "Intimidation", "Performance", "Persuasion"][:25]  # must be ≤25
    ]
)
async def roll_ability(interaction: discord.Interaction, roller: str, ability: str, advantage_override: str = "None"):
    if ability in ["STR", "DEX", "CON", "INT", "WIS", "CHA"]:
        #Regular stat check
        await interaction.response.send_message(":game_die: " + roller.title() + ", your  " + ability + " check rolled a: " + str(ability_check(roller, ability, "None", advantage_override)) + ".")
        return()
    else:
        #Ability check
        releventStat = "Unknown"
        if ability == "Athletics":
            releventStat = "STR"
        elif ability in ["Acrobatics", "Sleight of Hand", "Stealth"]:
            releventStat = "DEX"
        elif ability in ["Arcana", "History", "Investigation", "Nature", "Religion"]:
            releventStat = "INT"
        elif ability in ["Animal Handling", "Insight", "Medicine", "Perception", "Survival"]:
            releventStat = "WIS"
        elif ability in ["Deception", "Intimidation", "Performance", "Persuasion"]:
            releventStat = "CHA"
        await interaction.response.send_message(":game_die: " + roller.title() + ", your " + ability + " check rolled: " + str(ability_check(roller, releventStat, ability, advantage_override)) + ".")
#function to Roll X sided dice, Y times
def roll_dice(dice_count: int, dice_sides: int, modifier: int = 0) -> int:
    Total = modifier
    for i in range(dice_count):
        roll = random.randint(1, dice_sides)
        Total = Total + roll
    return(Total)

#function to Roll ability checks/saving throws
def ability_check(roller: str, abilityStat: str, abilityCheck: str, advantage: str = "None", passive: bool = False):
    #first get relevent information in the roller
    with open("Zed\\characters.csv") as characterFile:
        for line in characterFile.readlines():
            fields = line.split(",")  #Break line into list of values
            if fields[0].lower().startswith(roller.lower()):
                #If its the targets line
                rollerStatMods = fields[3].split("/") #List STR/DEX/CON/INT/WIS/CHA
                rollerProfBonus = int(fields[7])
                rollerProficiencies = fields[8].split("/") #List
                rollerSavingThrows = fields[9].split("/") #List

    statIndex = ["STR","DEX","CON","INT","WIS","CHA"].index(abilityStat.upper())
    modifier = int(rollerStatMods[statIndex])
    for ability in rollerProficiencies:
        if ability == abilityCheck:
            #If proficient also add the prof bonus
            modifier += rollerProfBonus
        if ability == abilityCheck+"X2":
            #If expert add prof bonus twice
            modifier += rollerProfBonus + rollerProfBonus
    abilityRoll = roll_dice(1, 20, modifier)
    
    Advantage = False
    Disadvantage = False
    if advantage.lower() == "advantage": Advantage = True
    elif advantage.lower() == "disadvantage": Disadvantage = True
    if Disadvantage or Advantage:
        alternateAbilityRoll = roll_dice(1, 20, modifier) #roll again
        if Disadvantage and alternateAbilityRoll < abilityRoll: abilityRoll = alternateAbilityRoll #Disadvantage, use it if its lower
        if Advantage and alternateAbilityRoll > abilityRoll: abilityRoll = alternateAbilityRoll #Advantage, use it if its higher
    if passive:
        #Take the average roll
        abilityRoll = 10 + modifier
    return(abilityRoll)
        

#function to roll damage (accounting for crits, resistances, immunities and vulrabilities)
def calc_damage(damage_dice: str, bonusToHit: int, damageMod: int, contestToHit: int, saveMod: int, damageType: str, targetVunResImm: str, Conditions: str, onSave: str, advantage_override: str):
                #e.g. 1d6, 2d10... ^add to the hit roll. ^Add to damage dice. ^e.g. targets AC, Spell Save DC. ^attackerConditions/targetConditions
    targetVunResImmParts = targetVunResImm.split("/")
    targetVulnerabilities = targetVunResImmParts[0]
    targetResistances = targetVunResImmParts[1]
    targetImmunities = targetVunResImmParts[2]
    crit = False
    saved = False

    attackerConditions = Conditions.split("/")[0]
    targetConditions = Conditions.split("/")[1]
    #Find if the attack(er) has advantage/disadvantage now
    advantageConditions = ["Invisible", "Hidden", "Surprised", "Flanking", "Helped", "FaerieFire", "GuidingBolt", "Unaware", "Advantage"]
    disadvantageConditions = ["Blinded", "Prone", "Poisoned", "Restrained", "Grappled", "Obscured", "Exhaustion", "Silenced", "Dodging", "Disadvantage"]
    #Defining conditions that grant advantage/impose disadvantage on the attacker
    Disadvantage = any(cond in disadvantageConditions for cond in attackerConditions) #Boolean
    Advantage = any(cond in advantageConditions for cond in targetConditions)         #Boolean
    if advantage_override == "disadvantage": Disadvantage = True
    elif advantage_override == "advantage": Advantage = True
    #Assigns the override value if given (defult is advantage_override = "None")
    rollToHit = roll_dice(1, 20, bonusToHit)
    #Takes the initial roll, we will now check on advantage and disadvantage to see if we roll again (and use that one instead)
    if Disadvantage and Advantage:
        #Normal roll (cancel out), this is needed otherwise disadvanatge would have priority over advantage
        rollToHit = rollToHit
    elif Disadvantage:
        #Disadvantage, roll again and use it if its lower
        alternateRollToHit = roll_dice(1, 20, bonusToHit)
        if alternateRollToHit < rollToHit: rollToHit = alternateRollToHit
    elif Advantage:
        #Advantage, roll again and use it if its higher
        alternateRollToHit = roll_dice(1, 20, bonusToHit)
        if alternateRollToHit > rollToHit: rollToHit = alternateRollToHit
                 
    if rollToHit < contestToHit + saveMod:
        #Attack missed the target
        saved = True
        #This wil be used at the end
    
    #Roll damage now
    diceCount = int(damage_dice.split("d")[0])
    diceSides = int(damage_dice.split("d")[1])
    damage = roll_dice(diceCount, diceSides, damageMod)
    if rollToHit-bonusToHit == 20 and "crit" not in targetImmunities.lower():
        #Natural 20 e.g. critical hit
        damage += roll_dice(diceCount, diceSides)
        crit = True
        #Roll the dice twice
    #Take into account damage type now
    if damageType in targetImmunities: damage = 0
    elif damageType in targetResistances: damage = int(damage/2)
    elif damageType in targetVulnerabilities: damage = damage*2
    if saved is True:
        if onSave == "Miss": damage = 0
        elif onSave == "Half": damage = int(damage/2)
    return(damage, damageType, rollToHit, saved, crit)

#Function to write to character file (apply damage and conditions to attacker/caster)
def apply_effects(attacker: str, target: str, damage: int, Conditions: str, DeathSave = "none") -> bool:
    conditionsToApply = Conditions.split("/")
    targetConditionsToApply = conditionsToApply[0]
    casterConditionsToApply = conditionsToApply[1]
    updatedCharFileLines = []
    targetZeroHp = False
    with open("Zed\\characters.csv") as characterFile:
        for line in characterFile.readlines():
            fields = line.split(",")  #Break line into list of values
            if fields[0].strip().lower() == target.strip().lower():
                #If its the targets line
                #Applying dmg
                hpValues = fields[4].split("/") #Split the HP field ("65/0/65") into parts
                if int(hpValues[1]) > int(damage) and int(damage) > 0:
                    #If the tempHp is higher than the dmg (and damage is positive, i.e. not healing)
                    hpValues[1] = str(max(0, int(hpValues[1]) - int(damage))) #Apply damage to the temp hp
                else:
                    #if the targets tempHp is less than total damage
                    damage -= int(hpValues[1]) #'absorb' the tempHp
                    hpValues[1] = "0" #set tempHp to none
                    hpValues[2] = str(max(0, int(hpValues[2]) - int(damage))) #Apply remainder damage
                if int(hpValues[2]) == 0:
                    targetZeroHp = True        
                fields[4] = "/".join(hpValues)

                #Apply New Conditions
                fields[12] = fields[12].strip() + targetConditionsToApply
                #Change other stats based on the conditions on the target
                for cond in fields[12].strip().split(" "):
                    if "Ac." in cond:
                        #If the condition modifies AC
                        acMod = int(cond[0:cond.index("Ac")])
                        fields[5] = str(int(fields[5])+acMod)
                        #Get the acMod and add it to the targets ac
                    if "save." in cond:
                        #If the condition gives/removes a stat save advantage
                        stat = cond[0:cond.index("save.")].upper() #includes the +/- at start
                        if stat.startswith("+"): #If it adds the save
                            fields[9] += "/" + stat[1:]
                        elif stat.startswith("-") and stat in fields[9]: #If it removes the save (and target already is prof in the save)
                            fields[9].remove("/" + stat[1:])
            if fields[0].strip().lower() == attacker.strip().lower():
                #If its the casters/attackers line
                #Apply New Conditions
                fields[12] = fields[12].strip() + casterConditionsToApply
                #Apply Death Save (if any)
                deathSaveValues = fields[10].split("/")
                if DeathSave == "success": fields[10] = str(int(deathSaveValues[0])+1) + "/" + deathSaveValues[1]
                if DeathSave == "fail": fields[10] = deathSaveValues[0] + "/" + str(int(deathSaveValues[1])+1)
            line = ",".join(fields)  #Rebuild the full line, which will later replace the original (thus updating the hp)
            #Now we add the adjusted line into a list
            updatedCharFileLines.append(line.strip())
            #with this list of strings (one string being one line of the csv) we can write it back into the file
    with open("Zed\\characters.csv", "w") as f:
        for line in updatedCharFileLines:
            f.write(line + "\n")
            #This will truncate the file (remove its contents) and write the updated lines in.
    return(targetZeroHp)

#Ideas to add:
    """
Add Fuzzy Matching with difflib (so minor spelling mistakes dont void a command)
Graphics of some kind to make it more user friendly and exciting to use, Somewhat used in encouter
DONE ~~Manual damage/healing & conditions for people who dont use the bot (like)~~
DONE ~~Hiding,Helping,Dodgeing~~
DONE ~~Allow a list of targets to be entered~~
REJECTED **Give feedback on hp values on attack** Reason: Most DM's wont want to reveal their monsters HP bar to the players. instead, if the 'character' is not marked with M- (for monster) I will give their remaining hp on turn start.
DONE ~~Add the moddifier to the dmg dice text~~
Done ~~Target yourself~~
Done ~~Abbility checks at will~~
Done ~~Create a character~~
    """

# Start the bot
client.run("MY_TOKEN")
