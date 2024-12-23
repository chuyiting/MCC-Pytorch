'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
    \file MCConvBuilder.py

    \brief Builder classes to create spatial convolutions and point hierarchies.

    \copyright Copyright (c) 2018 Visual Computing group of Ulm University,  
                Germany. See the LICENSE file at the top-level directory of 
                this distribution.

    \author pedro hermosilla (pedro-1.hermosilla-casajus@uni-ulm.de)
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

import sys
import os
import math
import torch
import torch.nn as nn
import torch.nn.init as init
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.append(os.path.join(ROOT_DIR, 'tf_ops'))
from pt_mcc.ops import compute_aabb, sort_points_step1, sort_points_step2, sort_features, sort_features_back, \
    compute_pdf, poisson_sampling, get_sampled_features, spatial_conv, get_block_size, transform_indices, find_neighbors


class PointHierarchy:
    """Class to compute and store a point hierarchy based on a given input point cloud.

    Attributes:
        points_ (list of nx3 tensors): List of point tensors. Each tensor correspond to
            a different level of the hierarchy, being the position 0 the input point cloud
            and the last level the coarse level of the hierarchy.
        features_ (list of nxm tensors): List of point feature tensor. Each tensor correspond
            to the point features of a different level of the hierarchy, following the same
            orther as the points_ list.
        batchIds_ (list of nx1 tensors): List of point batch ids tensor. Each tensor correspond
            to the point batch ids of a different level of the hierarchy, following the same
            orther as the points_ list.
        sampledIndexs_ (list of nx1 tensors): List of point indexs tensor. Each tensor correspond
            to the point indexs used to compute the next level of the hierarchy. This list follows
            the same orther as the points_list, however, this list has one element less since the 
            last level of the hierarchy was not used to compute another level.
        radiusList_ (list of float): List of Poisson Disk radius corresponding to each level of the
            hierarchy. Since the first level of the hierarchy is the input point cloud, the first
            element of the list is the 0.0.
        batchSize_ (int): Batch size used during computations.
        relativeRadius_ (bool): Boolean that indicates if the Poisson Disk radii are relative to 
            the bounding box of the point cloud.
        hierarchyName_ (string): Name of the point hierarchy. This string is used as a unique 
            identifier.
        aabbMin_ (batchSize_x3 tensor): List of minimum points of the bounding boxes for each point 
            cloud in the batch.
        aabbMax_ (batchSize_x3 tensor): List of maximum points of the bounding boxes for each point 
            cloud in the batch.
    """

    def __init__(self, 
        inPoints, inFeatures, inBatchIds, radiusList, 
        hierarchyName = "Point_Hierarchy", 
        batchSize = 32,
        relativeRadius = True):
        """Constructor.

        Args:
            inPoints (nx3 tensor): Input point positions.
            inFeatures (nxm tensor): Input point features.
            inBatchIds (nx1 tensor): Input point batch ids.
            radiusList (float array): List of radius used to compute the different 
                levels of the hierarchy.
            hierarchyName (string): Name of the point hierarchy.
            batchSize (int): Batch size used during the computations.
            relativeRadius (bool): Boolean that indicates if the radii are defined
                relative to the point cloud bounding box.
        """

        # Initialize the class variables.
        self.points_ = [inPoints]
        self.features_ =[inFeatures]
        self.batchIds_ = [inBatchIds]
        self.sampledIndexs_ = []
        self.radiusList_ = [0.0]
        self.batchSize_ = batchSize
        self.relativeRadius_ = relativeRadius
        self.hierarchyName_ = hierarchyName        

        # Compute the point cloud bounding box.
        aabbMin, aabbMax = compute_aabb(inPoints, inBatchIds, 
            batchSize, self.relativeRadius_)
        self.aabbMin_ = aabbMin
        self.aabbMax_ = aabbMax

        # print("")
        # print("########## Point Hierarchy: "+hierarchyName+" (Rel: "+str(relativeRadius)+")")
        # print("")
        # print("Level: 0 | Poisson Disk Radius: 0.0")

        # Initialize the temporal variables.
        currPts = inPoints
        currFeatures = inFeatures
        currBatchIds = inBatchIds

        # Compute the different levels.
        for level, currRadius in enumerate(radiusList):

            # print("Level: "+str(level+1)+" | Poisson Disk Radius: "+str(currRadius))

            # Distribute points into a regular grid.
            keys, indexs = sort_points_step1(currPts, currBatchIds, self.aabbMin_, 
                self.aabbMax_, self.batchSize_, currRadius, self.relativeRadius_)
            
            sortPts, sortBatchs, sortFeatures, cellIndexs = sort_points_step2(currPts, 
                currBatchIds, currFeatures, keys, indexs, self.aabbMin_, self.aabbMax_, 
                self.batchSize_, currRadius, self.relativeRadius_)

            # Use poisson disk sampling algorithm for the given radius.
            sampledPts, sampledBatchsIds, sampledIndexs = poisson_sampling(
                sortPts, sortBatchs, cellIndexs, aabbMin, aabbMax, currRadius, batchSize, self.relativeRadius_)
            sampledFeatures = get_sampled_features(sampledIndexs, sortFeatures)
            transformedIndexs = transform_indices(sampledIndexs, indexs)

            # Save the resulting point cloud.
            self.points_.append(sampledPts)
            self.batchIds_.append(sampledBatchsIds)
            self.features_.append(sampledFeatures)
            self.sampledIndexs_.append(transformedIndexs)
            self.radiusList_.append(currRadius)

            # Update temporal variables.
            currPts = sampledPts
            currBatchIds = sampledBatchsIds
            currFeatures = sampledFeatures
            

        # print("")


class ConvolutionBuilder (nn.Module):
    """Class to create the convolution operation on a point hierarchy.

    Attributes:
        multiFeatureConvs_ (bool): Boolean that indicates if the convolutions are multi 
            feature convolution or single feature convolutions. This default value can be 
            overwritten when creating a convolution.
        KDEWindow_ (float): Default window used in the kernel density estimation. This 
            default value can be overwritten when creating a convolution.
        relativeRadius_ (bool): Boolean that indicates if the radius is relative to the 
            bounding box of the point clouds. This default value can be overwritten when 
            creating a convolution.
        usePDF_ (bool): Boolean that indicates if the pdf is used during computations. 
            This default value can be overwritten when creating a convolution.
        useAVG_ (bool): Boolean that indicates if the convolution result is divided by
            the number of neighbors.
        decayLossCollection_ (string): Weight decay loss collection name.
        cacheGrids_ (dictionary of tuples (sortPts, sortBatchs, cellIndexs, indexs)): Cache
            of the resulting tensors of distributing points into a regular grid of a specific
            cell size.
        cacheNeighs_ (dictionary of tuples (startIndexs, packedNeighs)): Cache of the resulting
            tensors of computing the neighboring point for a given convolution.
        cachePDFs_ (dictionary of tensors): Cache of the resulting tensor of computing the PDF
            values for a list of neighboring points.
    """

    def __init__(self, 
        KDEWindow = 0.25,
        convName='',
        inPointLevel=2,
        outPointLevel=3,
        inNumFeatures = 0,
        outNumFeatures = -1,
        convRadius=math.sqrt(3.0)+0.1,
        multiFeatureConvs = False, 
        
        relativeRadius = True, # use default
        usePDF = False, # use default
        useAVG = True, # use default
        decayLossCollection = 'weight_decay_loss'):
        """Constructor.

        Args:
            multiFeatureConvs (bool): Boolean that indicates if the 
                convolutions are multi feature convolution or single
                feature convolutions. This default value can be 
                overwritten when creating a convolution.
            KDEWindow (float): Window used in the kernel density estimation.
                This default value can be overwritten when creating a convolution.
            relativeRadius (bool): Boolean that indicates if the radius
                is relative to the bounding box of the point clouds. This default 
                value can be overwritten when creating a convolution.
            usePDF (bool): Boolean that indicates if the pdf is
                used during computations. This default value can be 
                overwritten when creating a convolution.
            useAVG (bool): Boolean that indicates if the convolution result is 
                divided by the number of neighbors.
            decayLossCollection (string): Weight decay loss collection name.
        """
        super().__init__()
        # Initialize the caches.
        self.cacheGrids_ = {}
        self.cacheNeighs_ = {}
        self.cachePDFs_ = {}

        # Store the attributes.
        self.inPointLevel = inPointLevel
        self.outPointLevel = outPointLevel
        self.inNumFeatures = inNumFeatures
        self.outNumFeatures = inNumFeatures if outNumFeatures == -1 else outNumFeatures
        self.convRadius = convRadius

        self.multiFeatureConvs_ = multiFeatureConvs
        self.KDEWindow_ = KDEWindow
        self.relativeRadius_ = relativeRadius
        self.usePDF_ = usePDF
        self.useAVG_ = useAVG
        self.decayLossCollection_ = decayLossCollection

        print("########## Convolution Builder")
        print("")

        # Create the convolution.
        blockSize = get_block_size()
        
        if multiFeatureConvs:
            numOutNeurons = inNumFeatures * outNumFeatures
        else:
            numOutNeurons = inNumFeatures

        numBlocks = (numOutNeurons + blockSize - 1) // blockSize  # Equivalent to ceil(numOutNeurons / blockSize)

        print("Convolution: "+str(convName)+" (KDE: "+str(self.KDEWindow_)+" | MF: "+str(self.multiFeatureConvs_)+
            " | Rel: "+str(self.relativeRadius_)+" | PDF: "+str(self.usePDF_)+")")
        print("    In points: "+str(self.inPointLevel))
        print("    Out points: "+str(self.outPointLevel))
        print("    Features in: "+str(inNumFeatures))
        print("    Features out: "+str(self.outNumFeatures))
        print("    Radius: "+str(self.convRadius))

         # Initialize weights and biases
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.weights = nn.Parameter(torch.empty(3, blockSize * numBlocks, device=device))
        self.biases = nn.Parameter(torch.zeros(blockSize * numBlocks, device=device))
        self.weights2 = nn.Parameter(torch.empty(blockSize, numBlocks * blockSize, device=device))
        self.biases2 = nn.Parameter(torch.zeros(numBlocks * blockSize, device=device))
        self.weights3 = nn.Parameter(torch.empty(blockSize, numBlocks * blockSize, device=device))
        self.biases3 = nn.Parameter(torch.zeros(numBlocks * blockSize, device=device))

        init.xavier_normal_(self.weights)
        init.xavier_normal_(self.weights2)
        init.xavier_normal_(self.weights3)

    def __compute_dic_keys__(self,
        inPointHierarchy, outPointHierarchy,
        inPointLevel, outPointLevel,
        convRadius, KDEWindow, relativeRadius,
        usePDF):
        """Function to compute the dictionary keys for the operations: distribute
        the points into a regular grid, determine the neighboring points for a 
        given convolution, and compute the PDF values of each point.

        Args:
            inPointHierarchy (PointHierarchy): Input point hierarchy.
            outPointHierarchy (PointHierarchy): Output point hierarchy.
            inPointLevel (int): Level used of the input point hierarchy.
            outPointLevel (int): Level used of the output point hierarchy.
            convRadius (float): Radius of the convolutions.
            KDEWindow (float): Window used in the KDE.
            relativeRadius (bool): Boolean that indicates if the radius
                is relative to the bounding box of the point clouds.
            usePDF (bool): Boolean that indicates if the pdf will
                be used during computations.

        Returns:
            string: Dictionary key for the grid operations.
            string: Dictionary key for the find neighbors operation.
            string: Dictionary key for the compute pdfs operation.
        """
        
        keyGrid = inPointHierarchy.hierarchyName_ + '|' + str(inPointLevel) + '|' \
            + str(convRadius) + '|' + str(relativeRadius)

        keyNeighs = keyGrid + '|' + outPointHierarchy.hierarchyName_ + '|' \
            + str(outPointLevel) 

        keyPDF = keyNeighs + '|' + str(KDEWindow) + '|' + str(usePDF)
        
        return keyGrid, keyNeighs, keyPDF


    def reset(self):
        """Method to reset the cache of operations.
        """
        self.cacheGrids_ = {}
        self.cacheNeighs_ = {}
        self.cachePDFs_ = {}

    
    def forward(self,
        inPointHierarchy, 
        inFeatures):
        """Method to create a convolution layer. 
        
        This method uses a cache to store the operations to distribute points into a regular 
        grid, to find the neighboring points, and to compute the PDF values of the points. 
        By doing so, the builder avoids repeated computations in the final network architectures. 
        
        For some of the parameters (the ones with default value None) the default values 
        defined when create the class are used if no value is provided when the function is called.

        Args:
            convName (string): Name of the convolution.
            inPointHierarchy (PointHierarchy): Input point hierarchy.
            inPointLevel (int): Level used of the input point hierarchy.
            inFeatures (n1 x inNumFeatures tensor): Input features.
            inNumFeatures (int): Number of input features.
            convRadius (float): Radius of the convolution.
            outPointHierarchy (PointHierarchy): Output point hierarchy.
            outPointLevel (int): Level used of the output point hierarchy.
            multiFeatureConv (bool): Boolean that indicates if the 
                convolution is a multi feature convolution or asingle
                feature convolutions.
            outNumFeatures (int): Number of output features.
            KDEWindow (float): Window used in the KDE.
            relativeRadius (bool): Boolean that indicates if the radius
                is relative to the bounding box of the point clouds.
            usePDF (bool): Boolean that indicates if the pdf will
                be used during computations. 
            useAVG (bool): Boolean that indicates if the convolution result is 
                divided by the number of neighbors.

        Returns:
            n2 x outNumFeatures tensor: Convoluted feature tensor.
        """

        # Determine the configuration used for the convolution.
        currMultiFeatureConv = self.multiFeatureConvs_
        currNumOutFeatures = self.outNumFeatures
        currKDEWindow = self.KDEWindow_
        currRelativeRadius = self.relativeRadius_
        currUsePDF = self.usePDF_
        currUseAVG = self.useAVG_
        currOutPointHierarchy = inPointHierarchy
        currOutPointLevel = self.outPointLevel


        # Check if the batch size in both point hierarchies are the same.
        if currOutPointHierarchy.batchSize_ != inPointHierarchy.batchSize_:
            raise RuntimeError('Different batch size in the input and output point hierarchy')

        # Check if the num input features is equal to the number of output features 
        # when multifeatureCon is False
        if (currMultiFeatureConv == False) and (currNumOutFeatures!=self.inNumFeatures):
            raise RuntimeError('The number of input and output features should be the same ' \
                'for multi feature convolutions.')

        # Compute the keys used to access the dictionaries.
        keyGrid, keyNeighs, keyPDF = self.__compute_dic_keys__(inPointHierarchy, currOutPointHierarchy,
            self.inPointLevel, currOutPointLevel, self.convRadius, currKDEWindow, currRelativeRadius, currUsePDF)

        
        # Check if the grid distribution was already computed.
        if keyGrid in self.cacheGrids_:
            currGridTuple = self.cacheGrids_[keyGrid]
            sortFeatures = sort_features(inFeatures, currGridTuple[3])
        else:
            keys, indexs = sort_points_step1(inPointHierarchy.points_[self.inPointLevel], 
                inPointHierarchy.batchIds_[self.inPointLevel], inPointHierarchy.aabbMin_, 
                inPointHierarchy.aabbMax_, inPointHierarchy.batchSize_, 
                self.convRadius, currRelativeRadius)

            sortPts, sortBatchs, sortFeatures, cellIndexs = sort_points_step2(
                inPointHierarchy.points_[self.inPointLevel], 
                inPointHierarchy.batchIds_[self.inPointLevel], inFeatures, keys, indexs, 
                inPointHierarchy.aabbMin_, inPointHierarchy.aabbMax_, 
                inPointHierarchy.batchSize_, self.convRadius, currRelativeRadius)
            currGridTuple = (sortPts, sortBatchs, cellIndexs, indexs)
            #self.cacheGrids_[keyGrid] = currGridTuple

        # Check if the neighbor information was previously computed.
        if keyNeighs in self.cacheNeighs_:
            currNeighTuple = self.cacheNeighs_[keyNeighs]
            print('use neighbor cache')
        else:
            startIndexs, packedNeighs = find_neighbors(
                currOutPointHierarchy.points_[currOutPointLevel], 
                currOutPointHierarchy.batchIds_[currOutPointLevel], 
                currGridTuple[0], currGridTuple[2], inPointHierarchy.aabbMin_, 
                inPointHierarchy.aabbMax_, self.convRadius, inPointHierarchy.batchSize_, 
                currRelativeRadius)
            currNeighTuple = (startIndexs, packedNeighs)
            #self.cacheNeighs_[keyNeighs] = currNeighTuple

        # Check if the pdf was previously computed.
        if keyPDF in self.cachePDFs_:
            currPDFs = self.cachePDFs_[keyPDF]
        else:
            if currUsePDF:
                with torch.no_grad():
                    currPDFs = compute_pdf(currGridTuple[0], currGridTuple[1], 
                        inPointHierarchy.aabbMin_, inPointHierarchy.aabbMax_, 
                        currNeighTuple[0], currNeighTuple[1], currKDEWindow, self.convRadius, 
                        inPointHierarchy.batchSize_, currRelativeRadius)
            else:
                neighShape = currNeighTuple[1].shape
                currPDFs = torch.ones((neighShape[0], 1), dtype=torch.float32).cuda()

            #self.cachePDFs_[keyPDF] = currPDFs

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        num_out_features = torch.tensor(currNumOutFeatures, dtype=torch.int64).to(device=device)
        combin = torch.tensor(currMultiFeatureConv, dtype=torch.bool).to(device=device)
        batch_size = torch.tensor(inPointHierarchy.batchSize_, dtype=torch.int64).to(device=device)
        radius = torch.tensor(self.convRadius, dtype=torch.float).to(device=device)
        scale_inv = torch.tensor(currRelativeRadius, dtype=torch.bool).to(device=device)
        avg = torch.tensor(currUseAVG, dtype=torch.bool).to(device=device)
       
        conv1 = spatial_conv(currGridTuple[0], sortFeatures, currGridTuple[1], 
            currPDFs, currOutPointHierarchy.points_[currOutPointLevel], 
            currNeighTuple[0], currNeighTuple[1], 
            inPointHierarchy.aabbMin_, inPointHierarchy.aabbMax_, 
            self.weights, self.weights2, self.weights3, self.biases, self.biases2, self.biases3, 
            num_out_features, combin, batch_size, radius, scale_inv, avg)
        return conv1