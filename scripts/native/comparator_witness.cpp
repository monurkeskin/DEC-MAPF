#include "CBSNode.h"
#ifdef EECBS
#include "ECBSNode.h"
#endif
#include "SpaceTimeAStar.h"
#include <iostream>
int main() {
 CBSNode n; n.g_val=0; n.h_val=0;
 int violations=0;
#ifdef EECBS
 violations += CBSNode::compare_node_by_f{}(&n,&n);
 violations += CBSNode::compare_node_by_d{}(&n,&n);
 violations += CBSNode::compare_node_by_inadmissible_f{}(&n,&n);
 ECBSNode e;
 violations += ECBSNode::compare_node_by_f{}(&e,&e);
 violations += ECBSNode::compare_node_by_d{}(&e,&e);
 violations += ECBSNode::compare_node_by_inadmissible_f{}(&e,&e);
#else
 n.tie_breaking=0;
 violations += CBSNode::compare_node{}(&n,&n);
 violations += CBSNode::secondary_compare_node{}(&n,&n);
#endif
 AStarNode a(0,0,0,nullptr,0);
 violations += LLNode::compare_node{}(&a,&a);
 violations += LLNode::secondary_compare_node{}(&a,&a);
 std::cout << violations << std::endl;
 return violations ? 1 : 0;
}
