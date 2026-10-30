import unittest
import numpy as np
from hybrid import encode
from inspection_context import fill_check, recipe_context

class InspectionTests(unittest.TestCase):
    def test_clear_is_not_empty(self):
        result=fill_check(encode(np.full((200,100,3),200,np.uint8)))
        self.assertEqual(result['status'],'insufficient evidence')
    def test_constraints_and_previous_recipe(self):
        result=recipe_context(dict(recipe_id=7,tanks={'200':60,'300':30},dispense_order='T200>T300'),[dict(recipe_id=6,tanks={'100':30,'200':10},dispense_order='T200>T100')])
        self.assertEqual(result['previous_recipe'],6)
        self.assertEqual(len(result['warnings']),3)
        self.assertTrue(result['transition_risk'])
    def test_first_batch_has_unknown_predecessor(self):
        self.assertIsNone(recipe_context(dict(recipe_id=5,tanks={'100':10}),[])['previous_recipe'])

if __name__=='__main__': unittest.main()
