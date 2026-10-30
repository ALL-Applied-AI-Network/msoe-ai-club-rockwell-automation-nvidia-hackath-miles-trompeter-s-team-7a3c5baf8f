"""Read-only recipe context and conservative visible-fill checks."""
import cv2
import numpy as np
from hybrid import decode

def recipe_context(recipe, previous):
    prior=next((r for r in reversed(previous) if r['recipe_id']!=recipe['recipe_id']),None)
    tanks=recipe['tanks']; total=sum(tanks.values()); warnings=[]
    if total>80: warnings.append('Requested total exceeds the 80 mL limit')
    if tanks.get('300',0)>0: warnings.append('T-300 is out of service')
    if tanks.get('200',0)>50: warnings.append('T-200 request exceeds 50 mL')
    if any(0<v<10 or v>80 for v in tanks.values()): warnings.append('Selected component outside 10–80 mL range')
    return dict(current_recipe=recipe['recipe_id'],previous_recipe=prior['recipe_id'] if prior else None,previous_tanks=prior['tanks'] if prior else None,dispense_order=recipe.get('dispense_order'),previous_dispense_order=prior.get('dispense_order') if prior else None,requested_total_ml=total,warnings=warnings,transition_risk=bool(prior),explanation=(f"Recipe {prior['recipe_id']} preceded recipe {recipe['recipe_id']}. Residual mixture in the shared nozzle path may affect the first new fill. Dispense order is context, not proof of delivered amounts." if prior else 'No preceding different recipe is available. Do not infer a carryover source.'),provenance='project_desc.txt: T-100 clear, T-200 orange, T-400 blue; T-300 unavailable. No equipment commands are issued.')

def fill_check(image_url):
    """Visible colored-liquid surface proxy, not a calibrated volume estimate."""
    try:
        im=decode(image_url); h,w=im.shape[:2]
        hsv=cv2.cvtColor(im,cv2.COLOR_BGR2HSV)
        profile=np.median(hsv[int(h*.60):int(h*.95),int(w*.3):int(w*.7),1],axis=1)
        saturated=profile>40
        # Require a persistent colored region; clear liquid cannot be assessed.
        candidates=[i for i in range(max(0,len(profile)-5)) if saturated[i:i+5].all()]
        if not candidates: return dict(status='insufficient evidence',reason='No reliable colored-liquid surface; clear liquid or poor visibility cannot be classified as empty.')
        top=.60+candidates[0]/h
        if candidates[0]<3: return dict(status='insufficient evidence',reason='Liquid reaches the top of the unobstructed region; meniscus may be hidden by the rail.',visible_colored_height_fraction=round(.95-top,3))
        return dict(status='possible low fill - review' if top>.80 else 'visible surface detected',surface_y_fraction=round(top,3),visible_colored_height_fraction=round(.95-top,3),reason='Uncalibrated color-based surface proxy in lower vial body. No measured mL or overflow conclusion; glare and staining can mimic a surface.')
    except (ValueError,IndexError,cv2.error):
        return dict(status='insufficient evidence',reason='Cannot inspect vial image')
